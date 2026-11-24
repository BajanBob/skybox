#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 <your name>
"""
skybox-recon -- command-line engine (Beryl).

Reverse-engineering and reflash toolkit for ALi M3510/M3510A based satellite
receivers (Skybox F3/F4/F5/F5S/M3/V6).

Sole external dependency is pyserial, and only the hardware commands need it.

  selftest   offline checks, no hardware required
  uart       find the console baud rate and capture a transcript
  fw         entropy map, magic scan, carve a firmware dump
  static     strings extraction and Ghidra headless bootstrap
  ipl        IPL serial loader: probe / dump / write
  ymodem     YMODEM-1K sender, for U-Boot loady fallback
  usb        build a USB stick upgrade image
  tune       DVB-S/S2/S2X tuning via dvbv5-zap
  scan       spectral blind scan (rtl_power / hackrf_sweep) + advisor
  finder     satellite finder with audible beep
  pids       services, PIDs, codecs and satellite position from a .ts
  constel    constellation and MER from an IQ capture
  stream     serve a .ts to players on the local network
  lowsdr     SDR + leandvb for symbol rates the demod cannot reach
  remux      TS demux and decode pipelines

Frame: A5 5A | len:u16le | cmd:u8 | payload | crc32(body):u32le
Ack:   A5 5A 00 02 | cmd|0x80 | status:u8   (0 = OK)

WARNING: `ipl write` erases before writing. Read the stock flash with a
CH341A clip first. There is no undo.
"""
from __future__ import annotations

import argparse
import binascii
import hashlib
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from collections import Counter
from dataclasses import dataclass

VERSION = "6.0.0"
CODENAME = "Beryl"

# --------------------------------------------------------------------------- #
# common
# --------------------------------------------------------------------------- #

SYNC = b"\xa5\x5a"


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def crc32(data: bytes) -> int:
    return binascii.crc32(data) & 0xFFFFFFFF


def crc16_xmodem(data: bytes) -> int:
    crc = 0
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def sum16(data: bytes) -> int:
    return sum(data) & 0xFFFF


def hexdump(b: bytes, base: int = 0) -> str:
    out = []
    for i in range(0, len(b), 16):
        c = b[i:i + 16]
        hexs = " ".join(f"{x:02x}" for x in c)
        txt = "".join(chr(x) if 32 <= x < 127 else "." for x in c)
        out.append(f"{base + i:08x}  {hexs:<47}  {txt}")
    return "\n".join(out)


@dataclass
class Frame:
    cmd: int
    payload: bytes


def encode_frame(cmd: int, payload: bytes = b"") -> bytes:
    body = bytes([cmd]) + payload
    return SYNC + len(body).to_bytes(2, "little") + body + crc32(body).to_bytes(4, "little")


def decode_frame(buf: bytes) -> Frame | None:
    i = buf.find(SYNC)
    if i < 0 or len(buf) < i + 6:
        return None
    ln = int.from_bytes(buf[i + 2:i + 4], "little")
    if ln == 0 or len(buf) < i + 4 + ln + 4:
        return None
    body = buf[i + 4:i + 4 + ln]
    crc = int.from_bytes(buf[i + 4 + ln:i + 8 + ln], "little")
    if crc32(body) != crc:
        return None
    return Frame(body[0], body[1:])


def _serial():
    try:
        import serial  # noqa: PLC0415
    except ImportError:
        sys.exit("pyserial missing: pip install -r requirements.txt")
    return serial


PARITY = {"N": "PARITY_NONE", "E": "PARITY_EVEN", "O": "PARITY_ODD"}


def _parity(serial, key: str):
    return getattr(serial, PARITY[key])


# --------------------------------------------------------------------------- #
# recon: uart probe
# --------------------------------------------------------------------------- #

BAUDS = [115200, 57600, 38400, 19200, 9600, 230400, 460800]
TOKENS = [b"ALi", b"IPL", b"U-Boot", b"boot", b"Hit any", b"DRAM", b"Linux",
          b"#", b"=>", b"mtd", b"Skybox", b"3510", b"CRC"]


def _banner_score(b: bytes) -> float:
    if not b:
        return 0.0
    printable = sum(1 for c in b if 32 <= c < 127 or c in (9, 10, 13)) / len(b)
    return printable * len(b) + 40 * sum(t in b for t in TOKENS)


def cmd_uart(a):
    serial = _serial()
    p = _parity(serial, a.parity)
    sp = serial.Serial(a.port, 115200, 8, p, 1, timeout=0.05)
    print(f"probing {a.port} 8{a.parity}1 -- power-cycle the box now")
    best = (0.0, None)
    for baud in BAUDS:
        sp.baudrate = baud
        sp.reset_input_buffer()
        buf = b""
        end = time.time() + a.dwell
        while time.time() < end:
            buf += sp.read(4096)
        s = _banner_score(buf)
        print(f"  {baud:>7}  score={s:8.0f}  {len(buf):>5}B  {buf[:70]!r}")
        if s > best[0]:
            best = (s, baud)
    if not best[1]:
        sp.close()
        print("no usable baud rate found")
        return 1
    print(f"\nbest guess: {best[1]} 8{a.parity}1  (score {best[0]:.0f})")
    if a.capture:
        sp.baudrate = best[1]
        print(f"capturing to {a.capture} -- Ctrl-C to stop")
        with open(a.capture, "ab") as f:
            try:
                while True:
                    c = sp.read(4096)
                    if c:
                        f.write(c)
                        sys.stdout.buffer.write(c)
                        sys.stdout.flush()
            except KeyboardInterrupt:
                pass
    sp.close()
    return 0


# --------------------------------------------------------------------------- #
# recon: firmware container
# --------------------------------------------------------------------------- #

MAGICS = {
    b"\x27\x05\x19\x56": "uImage",
    b"\x1f\x8b": "gzip",
    b"\xfd7zXZ": "xz",
    b"\x28\xb5\x2f\xfd": "zstd",
    b"hsqs": "squashfs-le",
    b"sqsh": "squashfs-be",
    b"\x85\x19": "jffs2",
    b"\x31\x18\x10\x06": "ubifs",
    b"\xd0\x0d\xfe\xed": "fdt",
    b"ALi": "ali-magic",
}


def entropy(b: bytes) -> float:
    if not b:
        return 0.0
    c = Counter(b)
    n = len(b)
    return -sum((v / n) * math.log2(v / n) for v in c.values())


def entropy_map(data: bytes, win: int = 4096) -> None:
    print("entropy map (0.0 = zeros/text, 8.0 = compressed or encrypted)")
    for off in range(0, len(data), win * 16):
        row = [entropy(data[off + i:off + i + win]) for i in range(0, win * 16, win)]
        bar = "".join(" .:-=+*#%@"[min(9, int(e / 0.9))] for e in row)
        print(f"{off:08x} |{bar}| {sum(row) / len(row):.2f}")


def carve(data: bytes) -> None:
    for m, name in MAGICS.items():
        start = 0
        while (i := data.find(m, start)) >= 0:
            print(f"  {name:<14} @ 0x{i:08x}  {hexdump(data[i:i + 32], i)}")
            start = i + 1
    print("\ncandidate partition records (offset, size, crc):")
    for i in range(0, len(data) - 12, 4):
        off = int.from_bytes(data[i:i + 4], "little")
        size = int.from_bytes(data[i + 4:i + 8], "little")
        if 0x10000 <= off < len(data) and 0x1000 <= size < len(data) and off + size <= len(data):
            crc = int.from_bytes(data[i + 8:i + 12], "little")
            print(f"  0x{i:08x}: off=0x{off:08x} size=0x{size:08x} crc=0x{crc:08x}")


def cmd_fw(a):
    data = open(a.image, "rb").read()
    print(f"{a.image}: {len(data)} bytes  crc32={crc32(data):08x}  sha1={hashlib.sha1(data).hexdigest()}")
    print(hexdump(data[:256]))
    entropy_map(data)
    if a.carve:
        carve(data)
    if a.extract:
        os.makedirs(a.extract, exist_ok=True)
        n = 0
        for m, name in MAGICS.items():
            s = 0
            while (i := data.find(m, s)) >= 0:
                open(f"{a.extract}/{name}_{i:08x}.bin", "wb").write(data[i:i + 0x400000])
                s = i + 1
                n += 1
        log(f"extracted {n} regions to {a.extract}")
    return 0


# --------------------------------------------------------------------------- #
# recon: static analysis
# --------------------------------------------------------------------------- #

GHIDRA_SCRIPT = '''# ali_import.py -- Ghidra headless post-script
args = getScriptArgs()
base = int(args[0], 0)
print("image base 0x%x, entry guess 0x%x" % (base, base))
'''


def cmd_static(a):
    data = open(a.dump, "rb").read()
    for m in re.finditer(rb"[ -~]{%d,}" % a.minlen, data):
        print(f"{m.start():08x}  {m.group().decode('ascii', 'replace')}")
    for m in re.finditer(rb"(?:[ -~]\x00){%d,}" % a.minlen, data):
        print(f"{m.start():08x}  W  {m.group().decode('utf-16le', 'replace')}")
    if shutil.which("binwalk"):
        subprocess.run(["binwalk", "-B", a.dump], check=False)
    if a.ghidra:
        os.makedirs(a.ghidra, exist_ok=True)
        script = os.path.join(a.ghidra, "ali_import.py")
        open(script, "w").write(GHIDRA_SCRIPT)
        print(f"\nnow run:\n  analyzeHeadless {a.ghidra} skybox -import {a.dump} \\\n"
              f"    -processor {a.lang} -loader BinaryLoader -loader-baseAddr {a.base} \\\n"
              f"    -scriptPath {a.ghidra} -postScript ali_import.py {a.base}")
    return 0


# --------------------------------------------------------------------------- #
# flash: IPL serial loader
# --------------------------------------------------------------------------- #

OPCODES = {"hello": 0x01, "set_baud": 0x02, "info": 0x03, "erase": 0x10,
           "write": 0x11, "read": 0x12, "verify": 0x13, "jump": 0x20, "reset": 0x21}
BLOCK = 4096


class Loader:
    def __init__(self, port, baud=115200, parity="E", timeout=2.0):
        serial = _serial()
        self.sp = serial.Serial(port, baud, 8, _parity(serial, parity), 1,
                                timeout=0.05, write_timeout=timeout)
        self.buf = b""

    def _wait(self, want, timeout):
        deadline = time.time() + timeout
        while time.time() < deadline:
            chunk = self.sp.read(4096)
            if not chunk:
                continue
            self.buf += chunk
            f = decode_frame(self.buf)
            if f and f.cmd == want:
                cut = self.buf.find(SYNC) + 8
                self.buf = self.buf[cut:]
                if f.payload and f.payload[0] != 0:
                    raise RuntimeError(f"loader error 0x{f.payload[0]:02x}")
                return f
        return None

    def _xfer(self, name, payload=b"", timeout=3.0, retries=3):
        op = OPCODES[name]
        for attempt in range(1, retries + 1):
            self.sp.reset_input_buffer()
            self.sp.write(encode_frame(op, payload))
            f = self._wait(op | 0x80, timeout)
            if f is not None:
                return f
            log(f"  {name}: timeout ({attempt}/{retries})")
            time.sleep(0.15)
        raise RuntimeError(f"{name}: no ack after {retries} attempts")

    def info(self):
        p = self._xfer("hello").payload
        return {"chip_id": int.from_bytes(p[0:4], "big"),
                "flash_id": p[4:7].hex(),
                "flash_size": int.from_bytes(p[8:12], "big"),
                "ipl_version": p[12:28].split(b"\0")[0].decode("ascii", "replace")}

    def read(self, addr, size):
        out = bytearray()
        while len(out) < size:
            n = min(0x800, size - len(out))
            out += self._xfer("read", addr.to_bytes(4, "little") + n.to_bytes(2, "little"),
                              timeout=6.0).payload
        return bytes(out)

    def erase(self, addr, size):
        self._xfer("erase", addr.to_bytes(4, "little") + size.to_bytes(4, "little"), timeout=30.0)

    def write(self, addr, data):
        for off in range(0, len(data), BLOCK):
            self._xfer("write", (addr + off).to_bytes(4, "little") + data[off:off + BLOCK], timeout=6.0)
            log(f"\r  written {min(off + BLOCK, len(data))}/{len(data)}")


def cmd_ipl(a):
    ld = Loader(a.port, a.baud, a.parity)
    if a.action == "probe":
        print(ld.info())
    elif a.action == "dump":
        data = ld.read(a.addr, a.size)
        open(a.out, "wb").write(data)
        log(f"\nsaved {len(data)} bytes to {a.out}")
    elif a.action == "write":
        data = open(a.file, "rb").read()
        print(f"image {len(data)} bytes, crc32 {crc32(data):08x}")
        if not a.commit:
            log("dry run -- re-run with --commit")
            return 0
        if not a.no_erase:
            ld.erase(a.addr, len(data))
            log("erased")
        ld.write(a.addr, data)
        log("\nwrite done")
        ld._xfer("reset")
    return 0


# --------------------------------------------------------------------------- #
# flash: ymodem
# --------------------------------------------------------------------------- #

SOH, STX, EOT, ACK, NAK, CAN, CRC_C = 0x01, 0x02, 0x04, 0x06, 0x15, 0x18, 0x43


def _ypkt(hdr, blk, data):
    data = data.ljust(1024 if hdr == STX else 128, b"\x1a")
    body = bytes([blk & 0xFF, 0xFF - (blk & 0xFF)]) + data
    return bytes([hdr]) + body + crc16_xmodem(data).to_bytes(2, "big")


def _ywait(sp, want, timeout=10.0):
    sp.timeout = timeout
    while True:
        b = sp.read(1)
        if not b:
            return False
        if b[0] == want:
            return True
        if b[0] == CAN:
            return False


def ymodem_send(sp, path):
    name = os.path.basename(path).encode()
    size = os.path.getsize(path)
    if not _ywait(sp, CRC_C, 30):
        raise RuntimeError("no 'C' from receiver")
    sp.write(_ypkt(SOH, 0, f"{name}\0{size}".encode()))
    if not _ywait(sp, ACK):
        raise RuntimeError("header rejected")
    _ywait(sp, CRC_C)
    blk = 1
    with open(path, "rb") as f:
        while chunk := f.read(1024):
            sp.write(_ypkt(STX, blk, chunk))
            if not _ywait(sp, ACK):
                raise RuntimeError(f"NAK at block {blk}")
            blk = (blk + 1) & 0xFF
            log(f"\r  {min(blk * 1024, size)}/{size}")
    sp.write(bytes([EOT]))
    _ywait(sp, ACK)
    sp.write(_ypkt(SOH, 0, b""))
    _ywait(sp, ACK)
    log("\ntransfer complete")


def cmd_ymodem(a):
    serial = _serial()
    sp = serial.Serial(a.port, a.baud, 8, _parity(serial, a.parity), 1, timeout=10)
    try:
        ymodem_send(sp, a.file)
    finally:
        sp.close()
    return 0


# --------------------------------------------------------------------------- #
# flash: usb upgrade image
# --------------------------------------------------------------------------- #

USB_NAMES = {"f3": "Skybox_F3.abs", "f5": "Skybox_F5.abs", "f5s": "Skybox_F5S.abs",
             "m3": "Skybox_M3.abs", "allcode": "allcode.bin"}


def cmd_usb(a):
    data = open(a.image, "rb").read()
    name = USB_NAMES.get(a.model, f"Skybox_{a.model.upper()}.abs")
    shutil.copyfile(a.image, os.path.join(a.mount, name))
    with open(os.path.join(a.mount, name + ".crc"), "w") as f:
        f.write(f"{crc32(data):08x}\n")
    print(f"{name}: {len(data)} bytes, crc32 {crc32(data):08x}")
    print(f"bootloader included: {a.include_bootloader}")
    print("unmount cleanly, power off, insert, power on with POWER held")
    return 0


# --------------------------------------------------------------------------- #
# dvb: tuning
# --------------------------------------------------------------------------- #

def _tune_params(a):
    from skybox_recon.dvb import TuneParams
    return TuneParams(freq_khz=a.freq, sr=a.sr, delsys=a.delsys, mod=a.mod, fec=a.fec, pol=a.pol,
                      rolloff=a.rolloff, pilot=a.pilot, inversion=a.inversion, isi=a.mis,
                      pls_code=a.pls, pls_mode=a.pls_mode, sat_number=a.diseqc, service=a.service)


def tune_conf(a) -> str:
    from skybox_recon.dvb import dvbv5_conf
    return dvbv5_conf(_tune_params(a))


def cmd_tune(a):
    from skybox_recon.dvb import dvbv5_zap_cmd
    try:
        conf = tune_conf(a)
    except ValueError as e:
        raise RuntimeError(str(e))
    path = os.path.join(tempfile.gettempdir(), f"{a.service}.conf")
    with open(path, "w") as f:
        f.write(conf)
    cmd = dvbv5_zap_cmd(path, _tune_params(a), adapter=a.adapter, frontend=a.frontend, lnb=a.lnb, out=a.out)
    print(conf)
    print(" ".join(cmd))
    print("---", flush=True)
    if a.print_only:
        return 0
    os.execvp(cmd[0], cmd)


# --------------------------------------------------------------------------- #
# beryl: spectrum, blind scan, finder, PIDs, constellation, streaming
# --------------------------------------------------------------------------- #

def _sweeps(a):
    from skybox_recon import spectrum
    if a.csv:
        with open(a.csv, encoding="utf-8", errors="replace") as f:
            sweeps = spectrum.read_sweeps_csv(f.read())
    elif a.simulate:
        from skybox_recon.testsignals import demo_sweep
        print("SIMULATED test signal (not real reception)")
        sweeps = [demo_sweep(seed=1)]
    else:
        cmd = spectrum.sweep_command(a.tool, bin_khz=a.bin, gain=a.gain, once=True)
        print(" ".join(cmd), file=sys.stderr)
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        sweeps = spectrum.read_sweeps_csv(out.stdout)
        if not sweeps:
            raise RuntimeError(f"{a.tool} produced no data: {out.stderr.strip()[-300:]}")
    return sweeps


def cmd_scan(a):
    from skybox_recon import spectrum
    from skybox_recon.advisor import CognitiveAdvisor, identify_satellite, load_reference
    freqs, levels = _sweeps(a)[-1]
    found = spectrum.detect_transponders(freqs, levels, lof_mhz=a.lof, pol=a.pol, threshold_db=a.threshold)
    floor = spectrum.noise_floor(levels)
    print(f"sweep {freqs[0]:.0f}-{freqs[-1]:.0f} MHz IF, {len(freqs)} bins, noise floor {floor:.1f} dB")
    print(f"carriers: {len(found)} (LOF {a.lof:g} MHz, pol {a.pol}; symbol rates estimated from -3 dB width)")
    for t in found:
        print("  " + t.label())
    matches = identify_satellite(found, load_reference(a.reference)) if a.reference else None
    adv = CognitiveAdvisor()
    adv.record(found, a.lof, a.pol, floor)
    print("\nadvisor:")
    for tip in adv.advise(found, floor, a.lof, a.pol, reference_matches=matches):
        print("  " + str(tip))
    return 0


def cmd_finder(a):
    from skybox_recon import spectrum
    finder = spectrum.SatFinder(window=(a.window[0], a.window[1]) if a.window else None)
    if a.simulate:
        from skybox_recon.testsignals import demo_sweep
        print("SIMULATED test signal: level ramps up as if peaking the dish")
        for step in range(12):
            r = finder.update(*demo_sweep(gain=step / 11, seed=step))
            print(f"  C/N {r.cn_db:5.1f} dB  peak {r.peak_cn_db:5.1f}  tone {r.tone_hz} Hz"
                  f"{'  LOCK' if r.locked else ''}")
            if not a.silent:
                spectrum.play_tone(r.tone_hz, 400 if r.locked else 120)
        return 0
    cmd = spectrum.sweep_command(a.tool, a.window[0] if a.window else 950, a.window[1] if a.window else 2150,
                                 bin_khz=a.bin, gain=a.gain)
    print(" ".join(cmd) + "   (Ctrl-C to stop)")

    def on_sweep(f, l):
        r = finder.update(f, l)
        bar = "#" * int(r.quality * 40)
        print(f"\r  C/N {r.cn_db:5.1f} dB  peak {r.peak_cn_db:5.1f}  |{bar:<40}|{' LOCK' if r.locked else '     '}",
              end="", flush=True)
        if not a.silent:
            spectrum.play_tone(r.tone_hz, 400 if r.locked else 120)

    live = spectrum.LiveSweep(cmd, on_sweep, lambda m: print("\n" + m))
    live.start()
    try:
        while live.proc and live.proc.poll() is None:
            time.sleep(0.2)
    except KeyboardInterrupt:
        live.stop()
    return 0


def cmd_pids(a):
    from skybox_recon.ts_parser import analyze_file
    report = analyze_file(a.input, max_bytes=a.max_mb * 1024 * 1024)
    print(report.to_text())
    return 0 if report.packets else 1


def cmd_constel(a):
    from skybox_recon.constellation import load_iq, recover
    iq = load_iq(a.input, a.format)
    order = {"BPSK": 2, "QPSK": 4, "8PSK": 8}[a.mod]
    r = recover(iq, a.rate, a.sr, order=order, rolloff=a.rolloff)
    print(f"{a.mod}: {r.symbols.size} symbols  MER {r.mer_db:.1f} dB  EVM {r.evm_pct:.1f}%  "
          f"carrier offset {r.freq_offset_hz:+.0f} Hz")
    return 0


def cmd_stream(a):
    from skybox_recon.streamer import TSStreamServer
    srv = TSStreamServer(a.input, port=a.port, follow=a.follow, loop=not a.follow)
    srv.start()
    print("streaming on the local network (no internet used). Open in VLC/Kodi/mpv:")
    for u in srv.urls():
        print("  " + u)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        srv.stop()
    return 0


# --------------------------------------------------------------------------- #
# dvb: low symbol rate via SDR
# --------------------------------------------------------------------------- #

SRC = {"rtl": "rtl_sdr -f {f} -s {fs} -g {g} -",
       "airspy": "airspy_rx -f {f} -a {fs} -g {g} -r /dev/stdout",
       "pluto": "rx_sdr -f {f} -s {fs} -g {g} -F CF32 -"}


def cmd_lowsdr(a):
    for t in ("leandvb", a.src.replace("rtl", "rtl_sdr").split()[0]):
        if not shutil.which(t):
            sys.exit(f"missing: {t}")
    fs = min(max(int(a.sr * 1.4), 250_000), 2_400_000)
    rx = SRC[a.src].format(f=int(a.freq), fs=fs, g=a.gain)
    dvb = ["leandvb", "-f", str(fs), "--sr", str(a.sr), "--cr", a.cr,
           "--standard", a.std, "--fastlock", "--sampler", "rrc"]
    if a.std == "DVB-S2":
        dvb += ["--ldpc-helper", shutil.which("ldpc_tool") or "ldpc_tool",
                "--ldpc-iterations", "50"]
    tail = ["ffplay", "-"] if a.play else ["tee", a.out]
    line = " | ".join([rx, " ".join(dvb), " ".join(tail)])
    print(line, flush=True)
    os.execvp("sh", ["sh", "-c", line])


# --------------------------------------------------------------------------- #
# dvb: remux / decode
# --------------------------------------------------------------------------- #

PRESETS = {"copy": ["-c", "copy"],
           "modern": ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                      "-c:a", "aac", "-b:a", "192k", "-c:s", "copy"],
           "hevc": ["-c:v", "libx265", "-preset", "fast", "-crf", "23", "-c:a", "copy"],
           "av1": ["-c:v", "libsvtav1", "-preset", "6", "-crf", "30", "-c:a", "copy"]}

GST = ("gst-launch-1.0 filesrc location={i} ! tsdemux name=d "
       "d. ! queue ! h264parse ! v4l2slh264dec ! videoconvert ! autovideosink "
       "d. ! queue ! aacparse ! avdec_aac ! audioconvert ! autoaudiosink")


def cmd_remux(a):
    if a.preset == "gst":
        print(GST.format(i=a.input))
        return 0
    cmd = ["ffmpeg", "-hide_banner", "-i", a.input, "-map", a.map, *PRESETS[a.preset],
           "-max_muxing_queue_size", "4096", a.output or "-"]
    print(" ".join(cmd))
    if not a.print_only:
        os.execvp(cmd[0], cmd)
    return 0


# --------------------------------------------------------------------------- #
# selftest
# --------------------------------------------------------------------------- #

def cmd_selftest(a):
    fails = 0

    def check(name, cond):
        nonlocal fails
        print(f"  {'ok  ' if cond else 'FAIL'}  {name}")
        fails += 0 if cond else 1

    check("crc32 vector", crc32(b"123456789") == 0xCBF43926)
    check("crc16-xmodem vector", crc16_xmodem(b"123456789") == 0x31C3)
    check("sum16", sum16(b"\x01\x02\xff") == 0x0102)
    check("entropy zero block", entropy(b"\x00" * 4096) == 0.0)
    check("entropy random block", entropy(os.urandom(4096)) > 7.5)

    for cmd, payload in ((0x01, b""), (0x11, b"\x00\x10\x00\x00" + b"A" * 32)):
        f = decode_frame(encode_frame(cmd, payload))
        check(f"frame round-trip cmd 0x{cmd:02x}", f is not None and f.cmd == cmd and f.payload == payload)

    check("frame rejects bad crc", decode_frame(encode_frame(0x01) [:-1] + b"\x00") is None)

    with tempfile.TemporaryDirectory() as d:
        img = os.path.join(d, "synth.bin")
        blob = bytearray(b"\xff" * 0x10000)
        blob[0x100:0x104] = b"hsqs"
        blob[0x2000:0x2004] = b"\x27\x05\x19\x56"
        open(img, "wb").write(blob)
        out = os.path.join(d, "carved")
        cmd_fw(argparse.Namespace(image=img, carve=True, extract=out))
        check("carver finds squashfs", any(n.startswith("squashfs") for n in os.listdir(out)))
        check("carver finds uImage", any(n.startswith("uImage") for n in os.listdir(out)))

    # Beryl engines
    from skybox_recon import dvb, spectrum
    from skybox_recon.testsignals import DEMO_TRANSPONDERS, demo_sweep, demo_transport_stream
    from skybox_recon.ts_parser import TSParser
    p = TSParser()
    p.feed(demo_transport_stream())
    rep = p.report()
    check("TS parser: services and PIDs", len(rep.services) == 2 and
          {c.pid for s in rep.services for c in s.components} >= {0x200, 0x201, 0x300})
    check("TS parser: satellite position from NIT", rep.orbital_positions == ["28.2°E"])
    found = spectrum.detect_transponders(*demo_sweep(seed=5))
    check("blind scan finds all carriers", len(found) == len(DEMO_TRANSPONDERS))
    check("blind scan symbol-rate estimate",
          all(abs(t.sr_ksym / 1000 - sr) <= 1.6 for t, (_, sr, _) in zip(found, DEMO_TRANSPONDERS)))
    check("LNB arithmetic", dvb.if_to_rf(1028, 9750) == 10778 and dvb.if_to_rf(1000, 5150) == 4150)
    check("dvbv5 modulation names", "MODULATION = PSK/8" in dvb.dvbv5_conf(
        dvb.TuneParams(freq_khz=11778000, sr=27500000, mod="8PSK")))
    check("finder tone rises with signal", spectrum.SatFinder().update(*demo_sweep(gain=1.0)).tone_hz
          > spectrum.SatFinder().update(*demo_sweep(gain=0.2)).tone_hz)
    try:
        from skybox_recon.constellation import recover
        from skybox_recon.testsignals import demo_iq
        r = recover(demo_iq(snr_db=20), 4e6, 1e6)
        check("constellation QPSK MER", r.mer_db > 20)
    except ImportError:
        print("  skip  constellation (numpy not installed)")

    print(f"\n{fails} failure(s)")
    return 1 if fails else 0


# --------------------------------------------------------------------------- #
# cli
# --------------------------------------------------------------------------- #

def build_parser():
    ap = argparse.ArgumentParser(prog="skybox.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-V", "--version", action="version", version=f"%(prog)s {VERSION}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("selftest", help="offline checks").set_defaults(fn=cmd_selftest)

    u = sub.add_parser("uart", help="console discovery")
    u.add_argument("port")
    u.add_argument("--parity", default="E", choices=list("NEO"))
    u.add_argument("--dwell", type=float, default=1.0)
    u.add_argument("--capture")
    u.set_defaults(fn=cmd_uart)

    f = sub.add_parser("fw", help="analyse a firmware dump")
    f.add_argument("image")
    f.add_argument("--carve", action="store_true")
    f.add_argument("--extract")
    f.set_defaults(fn=cmd_fw)

    s = sub.add_parser("static", help="strings and Ghidra bootstrap")
    s.add_argument("dump")
    s.add_argument("--minlen", type=int, default=5)
    s.add_argument("--ghidra")
    s.add_argument("--base", default="0x80000000")
    s.add_argument("--lang", default="MIPS:BE:32:default")
    s.set_defaults(fn=cmd_static)

    i = sub.add_parser("ipl", help="IPL serial loader")
    i.add_argument("port")
    i.add_argument("action", choices=["probe", "dump", "write"])
    i.add_argument("--baud", type=int, default=115200)
    i.add_argument("--parity", default="E", choices=list("NEO"))
    i.add_argument("addr", nargs="?", type=lambda x: int(x, 0), default=0)
    i.add_argument("arg", nargs="?", default="")
    i.add_argument("--size", type=lambda x: int(x, 0), default=0)
    i.add_argument("--out", default="dump.bin")
    i.add_argument("--no-erase", action="store_true")
    i.add_argument("--commit", action="store_true")
    i.set_defaults(fn=cmd_ipl)

    y = sub.add_parser("ymodem", help="YMODEM-1K sender")
    y.add_argument("port")
    y.add_argument("file")
    y.add_argument("--baud", type=int, default=115200)
    y.add_argument("--parity", default="N", choices=list("NEO"))
    y.set_defaults(fn=cmd_ymodem)

    b = sub.add_parser("usb", help="build a USB upgrade image")
    b.add_argument("image")
    b.add_argument("mount")
    b.add_argument("--model", default="f5s")
    b.add_argument("--include-bootloader", action="store_true")
    b.set_defaults(fn=cmd_usb)

    from skybox_recon import dvb as _dvb
    t = sub.add_parser("tune", help="DVB-S/S2/S2X tuning via dvbv5-zap")
    t.add_argument("--adapter", type=int, default=0)
    t.add_argument("--frontend", type=int, default=0)
    t.add_argument("--delsys", default="DVBS2", choices=list(_dvb.MODULATIONS))
    t.add_argument("--freq", type=int, required=True, help="RF frequency, kHz")
    t.add_argument("--sr", type=int, required=True, help="symbols/s")
    t.add_argument("--fec", default="auto", choices=_dvb.FEC)
    t.add_argument("--mod", default="auto", choices=_dvb.ALL_MODULATIONS)
    t.add_argument("--rolloff", default="auto", choices=_dvb.ROLLOFF)
    t.add_argument("--pilot", default="auto", choices=_dvb.PILOT)
    t.add_argument("--inversion", default="auto", choices=_dvb.INVERSION)
    t.add_argument("--pol", default="H", choices=["H", "V", "L", "R"])
    t.add_argument("--mis", type=int, help="input stream ID (multistream)")
    t.add_argument("--pls", type=int, help="PLS code")
    t.add_argument("--pls-mode", default="ROOT", choices=_dvb.PLS_MODES)
    t.add_argument("--diseqc", type=int, choices=range(4), help="DiSEqC port 0-3")
    t.add_argument("--lnb", default="UNIVERSAL", choices=list(_dvb.LNBS))
    t.add_argument("--service", default="ch1")
    t.add_argument("--out", default="pipe:1")
    t.add_argument("--print-only", action="store_true", help="show the channel file and command only")
    t.set_defaults(fn=cmd_tune)

    def sweep_args(p):
        p.add_argument("--tool", default="rtl_power", choices=["rtl_power", "hackrf_sweep"])
        p.add_argument("--csv", help="read a saved rtl_power/hackrf_sweep CSV instead of live capture")
        p.add_argument("--simulate", action="store_true", help="use the built-in SIMULATED test signal")
        p.add_argument("--bin", type=int, default=1000, help="bin width, kHz")
        p.add_argument("--gain", type=int, default=30)

    sc = sub.add_parser("scan", help="spectral blind scan of the 950-2150 MHz IF band")
    sweep_args(sc)
    sc.add_argument("--lof", type=float, default=9750.0, help="LNB local oscillator, MHz")
    sc.add_argument("--pol", default="H", choices=["H", "V", "L", "R"])
    sc.add_argument("--threshold", type=float, default=3.0, help="dB above noise floor")
    sc.add_argument("--reference", help="transponder list CSV for satellite pattern matching")
    sc.set_defaults(fn=cmd_scan)

    fi = sub.add_parser("finder", help="satellite finder with audible beep")
    sweep_args(fi)
    fi.add_argument("--window", type=float, nargs=2, metavar=("LO_MHZ", "HI_MHZ"), help="IF window to watch")
    fi.add_argument("--silent", action="store_true")
    fi.set_defaults(fn=cmd_finder)

    pi = sub.add_parser("pids", help="services, PIDs and satellite position from a .ts recording")
    pi.add_argument("input")
    pi.add_argument("--max-mb", type=int, default=64)
    pi.set_defaults(fn=cmd_pids)

    co = sub.add_parser("constel", help="constellation and MER from an IQ capture")
    co.add_argument("input")
    co.add_argument("--rate", type=float, required=True, help="capture sample rate, S/s")
    co.add_argument("--sr", type=float, required=True, help="symbol rate, sym/s")
    co.add_argument("--mod", default="QPSK", choices=["BPSK", "QPSK", "8PSK"])
    co.add_argument("--rolloff", type=float, default=0.35)
    co.add_argument("--format", default="auto", choices=["auto", "cu8", "cs8", "cf32"])
    co.set_defaults(fn=cmd_constel)

    st = sub.add_parser("stream", help="stream a .ts to players on the local network")
    st.add_argument("input")
    st.add_argument("--port", type=int, default=8090)
    st.add_argument("--follow", action="store_true", help="follow a file that is still being written")
    st.set_defaults(fn=cmd_stream)

    l = sub.add_parser("lowsdr", help="SDR + leandvb low symbol rate")
    l.add_argument("--src", default="rtl", choices=SRC)
    l.add_argument("--freq", type=float, required=True, help="Hz")
    l.add_argument("--sr", type=float, required=True, help="symbols/s")
    l.add_argument("--cr", default="1/2")
    l.add_argument("--std", default="DVB-S2", choices=["DVB-S", "DVB-S2"])
    l.add_argument("--gain", default="28")
    l.add_argument("--out", default="out.ts")
    l.add_argument("--play", action="store_true")
    l.set_defaults(fn=cmd_lowsdr)

    r = sub.add_parser("remux", help="demux / decode pipelines")
    r.add_argument("input")
    r.add_argument("output", nargs="?")
    r.add_argument("--preset", default="copy", choices=list(PRESETS) + ["gst"])
    r.add_argument("--map", default="0")
    r.add_argument("--print-only", action="store_true")
    r.set_defaults(fn=cmd_remux)

    return ap


def _pause_if_double_clicked():
    """Keep a double-clicked Windows console open so the output can be read."""
    if os.name == "nt" and getattr(sys, "frozen", False) and sys.stdin and sys.stdin.isatty():
        try:
            input("\nPress Enter to close this window...")
        except (EOFError, OSError):
            pass


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    parser = build_parser()
    if not argv:
        # Started with no command (e.g. double-clicked): explain instead of
        # printing an argparse error and closing instantly.
        parser.print_help()
        print("\nThis is the command-line engine. For the desktop window run "
              "SkyboxRecon.exe (or `python skybox_gui.py`).")
        _pause_if_double_clicked()
        return 0
    a = parser.parse_args(argv)
    try:
        return a.fn(a) or 0
    except RuntimeError as e:
        log(f"error: {e}")
        return 1
    except FileNotFoundError as e:
        log(f"error: {e.strerror or e}: {e.filename or 'required program'}. Check the "
            "path, or install the external tool this command needs "
            "(e.g. dvbv5-zap, leandvb, ffmpeg).")
        return 2
    except OSError as e:
        log(f"error: {e}")
        return 1
    except KeyboardInterrupt:
        log("\ninterrupted")
        return 130


if __name__ == "__main__":
    sys.exit(main())