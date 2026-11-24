"""Synthetic test signals: a small DVB transport stream, spectrum sweeps and
QPSK/8PSK IQ samples. Used by the self-tests and by the GUI's clearly labelled
"Simulated test signal" source; never presented as real reception.
"""
from __future__ import annotations

import math
import random

from .ts_parser import crc32_mpeg2

# --------------------------------------------------------------------------- #
# MPEG-TS
# --------------------------------------------------------------------------- #


def _section(table_id: int, ext: int, body: bytes, version: int = 0) -> bytes:
    length = 5 + len(body) + 4
    head = bytes([table_id, 0xB0 | ((length >> 8) & 0x0F), length & 0xFF,
                  ext >> 8, ext & 0xFF, 0xC1 | (version << 1), 0, 0])
    sec = head + body
    return sec + crc32_mpeg2(sec).to_bytes(4, "big")


def _desc(tag: int, data: bytes) -> bytes:
    return bytes([tag, len(data)]) + data


def _bcd(value: int, digits: int) -> bytes:
    s = str(value).rjust(digits, "0")
    if len(s) % 2:
        s += "0"
    return bytes(int(s[i]) << 4 | int(s[i + 1]) for i in range(0, len(s), 2))


def packetize(pid: int, section: bytes, cc_start: int = 0) -> list[bytes]:
    payload = bytes([0]) + section  # pointer_field = 0
    packets = []
    cc = cc_start
    first = True
    while payload:
        chunk, payload = payload[:184], payload[184:]
        head = bytes([0x47, (0x40 if first else 0) | (pid >> 8), pid & 0xFF, 0x10 | (cc & 0x0F)])
        packets.append(head + chunk.ljust(184, b"\xff"))
        cc += 1
        first = False
    return packets


def demo_transport_stream(repeat: int = 3) -> bytes:
    """Two services, one scrambled, a NIT announcing two transponders at 28.2°E."""
    tsid, onid, nid = 0x07D4, 0x0002, 0x0002
    pat = _section(0x00, tsid, bytes([0x00, 0x00, 0xE0, 0x10,       # NIT on PID 0x10
                                      0x00, 0x65, 0xE1, 0x00,       # service 101 -> PMT 0x100
                                      0x00, 0x66, 0xE1, 0x10]))     # service 102 -> PMT 0x110

    def pmt(prog: int, pcr: int, streams: list[tuple[int, int, bytes]], ca: bool) -> bytes:
        pinfo = _desc(0x09, bytes([0x0B, 0x00, 0xE7, 0xFF])) if ca else b""
        body = bytes([0xE0 | (pcr >> 8), pcr & 0xFF, 0xF0 | (len(pinfo) >> 8), len(pinfo) & 0xFF]) + pinfo
        for stype, pid, descs in streams:
            body += bytes([stype, 0xE0 | (pid >> 8), pid & 0xFF, 0xF0 | (len(descs) >> 8), len(descs) & 0xFF]) + descs
        return _section(0x02, prog, body)

    pmt1 = pmt(101, 0x200, [
        (0x24, 0x200, b""),                                                    # HEVC video
        (0x06, 0x201, _desc(0x7A, b"\x00") + _desc(0x0A, b"eng\x00")),          # E-AC-3, English
        (0x11, 0x202, _desc(0x0A, b"spa\x00")),                                 # AAC LATM, Spanish
        (0x06, 0x203, _desc(0x59, b"eng\x10\x00\x01\x00\x01")),                 # DVB subtitles
    ], ca=False)
    pmt2 = pmt(102, 0x300, [
        (0x1B, 0x300, b""),                                                    # H.264 video
        (0x06, 0x301, _desc(0x7F, b"\x15\x00") + _desc(0x0A, b"fra\x00")),      # AC-4, French
    ], ca=True)

    def service(sid: int, stype: int, provider: str, name: str, ca: bool) -> bytes:
        d = _desc(0x48, bytes([stype, len(provider) + 1]) + b"\x15" + provider.encode()
                  + bytes([len(name.encode()) + 1]) + b"\x15" + name.encode())
        return bytes([sid >> 8, sid & 0xFF, 0xFC, 0x80 | (0x10 if ca else 0) | (len(d) >> 8), len(d) & 0xFF]) + d

    sdt = _section(0x42, tsid, bytes([onid >> 8, onid & 0xFF, 0xFF])
                   + service(101, 0x1F, "Skybox Test", "Test Card UHD", False)
                   + service(102, 0x19, "Skybox Test", "Météo HD", True))

    def sat(freq_khz: int, orbital_tenths: int, east: bool, pol: int, s2: bool, mod: int, sr: int, fec: int) -> bytes:
        flags = (0x80 if east else 0) | (pol << 5) | (0x04 if s2 else 0) | mod
        return _desc(0x43, _bcd(freq_khz // 10, 8) + _bcd(orbital_tenths, 4) + bytes([flags])
                     + _bcd(sr // 100, 7)[:3] + bytes([(_bcd(sr // 100, 7)[3] & 0xF0) | fec]))

    name = _desc(0x40, b"Skybox Test Network")
    loop = b""
    for t, freq, pol, s2, mod, sr, fec in ((tsid, 11_778_000, 1, True, 2, 27_500_000, 3),
                                           (0x07D5, 10_847_000, 0, False, 1, 23_000_000, 4)):
        d = sat(freq, 282, True, pol, s2, mod, sr, fec)
        loop += bytes([t >> 8, t & 0xFF, onid >> 8, onid & 0xFF, 0xF0 | (len(d) >> 8), len(d) & 0xFF]) + d
    nit = _section(0x40, nid, bytes([0xF0 | (len(name) >> 8), len(name) & 0xFF]) + name
                   + bytes([0xF0 | (len(loop) >> 8), len(loop) & 0xFF]) + loop)

    out = bytearray()
    cc: dict[int, int] = {}
    for _ in range(repeat):
        for pid, sec in ((0x00, pat), (0x100, pmt1), (0x110, pmt2), (0x11, sdt), (0x10, nit)):
            pkts = packetize(pid, sec, cc.get(pid, 0))
            cc[pid] = cc.get(pid, 0) + len(pkts)
            out += b"".join(pkts)
        for pid in (0x200, 0x201, 0x300):
            c = cc.get(pid, 0)
            scr = 0x80 if pid == 0x300 else 0
            out += bytes([0x47, pid >> 8, pid & 0xFF, scr | 0x10 | (c & 0x0F)]) + bytes(184)
            cc[pid] = c + 1
        out += bytes([0x47, 0x1F, 0xFF, 0x10]) + b"\xff" * 184   # null packet
    return bytes(out)


# --------------------------------------------------------------------------- #
# spectrum
# --------------------------------------------------------------------------- #

DEMO_TRANSPONDERS = (  # (IF centre MHz, symbol rate Msym/s, level dB above floor)
    (1028.0, 27.5, 14.0), (1178.0, 22.0, 18.0), (1394.0, 30.0, 11.0),
    (1612.0, 7.2, 9.0), (1745.0, 27.5, 16.0), (1903.0, 3.0, 8.0), (2048.0, 30.0, 12.0))


def demo_sweep(start_mhz: float = 950.0, stop_mhz: float = 2150.0, step_mhz: float = 1.0,
               floor_db: float = -92.0, gain: float = 1.0, seed: int | None = None,
               rolloff: float = 0.2) -> tuple[list[float], list[float]]:
    """A simulated L-band IF sweep with raised-cosine shaped transponders."""
    rnd = random.Random(seed)
    freqs, levels = [], []
    f = start_mhz
    while f <= stop_mhz + 1e-9:
        p = 10 ** (floor_db / 10)
        for centre, sr, lvl in DEMO_TRANSPONDERS:
            half = sr / 2
            x = abs(f - centre)
            edge0, edge1 = half * (1 - rolloff), half * (1 + rolloff)
            if x <= edge0:
                shape = 1.0
            elif x <= edge1:
                shape = 0.5 * (1 + math.cos(math.pi * (x - edge0) / (edge1 - edge0)))
            else:
                shape = 0.0
            p += shape * 10 ** ((floor_db + lvl * gain) / 10)
        freqs.append(round(f, 6))
        levels.append(10 * math.log10(p) + rnd.gauss(0, 0.6))
        f += step_mhz
    return freqs, levels


def demo_rtl_power_csv(sweeps: int = 2, seed: int = 1) -> str:
    """The same sweep in rtl_power / hackrf_sweep CSV format."""
    lines = []
    for n in range(sweeps):
        freqs, levels = demo_sweep(seed=seed + n)
        for i in range(0, len(freqs) - 1, 100):
            chunk = levels[i:i + 100]
            lo = int(freqs[i] * 1e6)
            hi = int((freqs[i] + len(chunk)) * 1e6)
            lines.append(f"2026-11-24, 12:00:0{n}, {lo}, {hi}, 1000000.00, 64, "
                         + ", ".join(f"{v:.2f}" for v in chunk))
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- #
# IQ
# --------------------------------------------------------------------------- #

def demo_iq(symbols: int = 4000, sps: int = 4, order: int = 4, snr_db: float = 20.0,
            freq_offset: float = 0.002, phase: float = 0.6, rolloff: float = 0.35, seed: int = 7):
    """Complex baseband PSK samples (numpy array) with RRC shaping, offset and noise."""
    import numpy as np

    from .constellation import rrc_taps

    rng = np.random.default_rng(seed)
    idx = rng.integers(0, order, symbols)
    syms = np.exp(1j * (2 * np.pi * idx / order + (np.pi / order if order == 4 else 0)))
    up = np.zeros(symbols * sps, complex)
    up[::sps] = syms
    tx = np.convolve(up, rrc_taps(sps, rolloff, 12), mode="same")
    tx /= np.sqrt(np.mean(np.abs(tx) ** 2))
    n = np.arange(tx.size)
    tx = tx * np.exp(1j * (2 * np.pi * freq_offset * n + phase))
    noise = (rng.standard_normal(tx.size) + 1j * rng.standard_normal(tx.size)) / np.sqrt(2)
    return tx + noise * 10 ** (-snr_db / 20)
