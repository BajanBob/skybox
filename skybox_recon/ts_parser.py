"""MPEG-TS service and PID discovery (PAT, PMT, SDT, NIT) for Skybox Recon.

Reads a recorded or live transport stream and reports services, their video,
audio, subtitle and PCR PIDs, codec candidates, scrambling, and the satellite
delivery parameters (including orbital position) the network announces in the
NIT. Pure Python, no decoding of audio or video.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .audio_codecs import get_codec, identify_audio_candidate
from .tuner_topology import PIDComponent, ServiceRecord

TS_PACKET = 188
SYNC = 0x47

VIDEO_STREAM_TYPES = {
    0x01: "MPEG-1 Video",
    0x02: "MPEG-2 Video",
    0x10: "MPEG-4 Visual",
    0x1B: "H.264 / AVC",
    0x24: "H.265 / HEVC",
    0x33: "H.266 / VVC",
}
# MPEG-H 3D Audio main stream (MHAS) is carried as stream_type 0x2D.
EXTRA_AUDIO_STREAM_TYPES = {0x2D: "mpeg-h-lc"}
# DVB extension_descriptor (0x7F) tag_extension values that identify audio.
AUDIO_EXTENSION_TAGS = {0x15: "ac4", 0x0E: "dts-hd"}

SERVICE_TYPES = {
    0x01: "TV (SD)", 0x02: "Radio", 0x0A: "Radio (advanced codec)", 0x0C: "Data",
    0x11: "TV (MPEG-2 HD)", 0x16: "TV (H.264 SD)", 0x19: "TV (H.264 HD)",
    0x1C: "TV (H.264 3D)", 0x1F: "TV (HEVC)", 0x20: "TV (HEVC UHD)",
}
POLARIZATION = ("H", "V", "L", "R")
SAT_MODULATION = ("auto", "QPSK", "8PSK", "16QAM")
SAT_ROLLOFF = ("0.35", "0.25", "0.20", "reserved")
FEC_INNER = {1: "1/2", 2: "2/3", 3: "3/4", 4: "5/6", 5: "7/8", 6: "8/9", 7: "3/5",
             8: "4/5", 9: "9/10", 15: "none"}


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

def crc32_mpeg2(data: bytes) -> int:
    crc = 0xFFFFFFFF
    for b in data:
        crc ^= b << 24
        for _ in range(8):
            crc = ((crc << 1) ^ 0x04C11DB7) & 0xFFFFFFFF if crc & 0x80000000 else (crc << 1) & 0xFFFFFFFF
    return crc


def bcd(data: bytes, digits: int) -> int:
    value = 0
    for i in range(digits):
        byte = data[i // 2]
        nib = (byte >> 4) if i % 2 == 0 else (byte & 0x0F)
        value = value * 10 + (nib if nib < 10 else 0)
    return value


def dvb_text(raw: bytes) -> str:
    """Decode a DVB string (EN 300 468 Annex A) as far as Python codecs allow."""
    if not raw:
        return ""
    first = raw[0]
    encoding, body = "latin-1", raw
    if first == 0x15:
        encoding, body = "utf-8", raw[1:]
    elif first == 0x10 and len(raw) >= 3:
        encoding, body = f"iso-8859-{raw[2]}", raw[3:]
    elif 0x01 <= first <= 0x0B:
        encoding, body = f"iso-8859-{first + 4}", raw[1:]
    elif first == 0x11:
        encoding, body = "utf-16-be", raw[1:]
    elif first < 0x20:
        body = raw[1:]
    try:
        text = body.decode(encoding, "replace")
    except LookupError:
        text = body.decode("latin-1", "replace")
    return "".join(ch for ch in text if ch >= " " and not "\x80" <= ch <= "\x9f").strip()


def iter_descriptors(data: bytes):
    i = 0
    while i + 2 <= len(data):
        tag, length = data[i], data[i + 1]
        yield tag, data[i + 2:i + 2 + length]
        i += 2 + length


# --------------------------------------------------------------------------- #
# results
# --------------------------------------------------------------------------- #

@dataclass
class SatelliteDelivery:
    transport_stream_id: int
    original_network_id: int
    frequency_khz: int
    orbital_position: float          # degrees
    east: bool
    polarization: str
    modulation_system: str           # DVB-S or DVB-S2
    modulation: str
    roll_off: str | None
    symbol_rate: int                 # symbols/s
    fec: str

    @property
    def orbital_label(self) -> str:
        return f"{self.orbital_position:.1f}°{'E' if self.east else 'W'}"


@dataclass
class StreamReport:
    packets: int = 0
    sync_errors: int = 0
    transport_stream_id: int | None = None
    original_network_id: int | None = None
    network_id: int | None = None
    network_name: str | None = None
    services: list[ServiceRecord] = field(default_factory=list)
    service_types: dict[int, str] = field(default_factory=dict)
    providers: dict[int, str] = field(default_factory=dict)
    deliveries: list[SatelliteDelivery] = field(default_factory=list)
    pid_counts: dict[int, int] = field(default_factory=dict)
    scrambled_pids: set[int] = field(default_factory=set)
    cc_errors: int = 0
    crc_errors: int = 0

    @property
    def this_transponder(self) -> SatelliteDelivery | None:
        for d in self.deliveries:
            if d.transport_stream_id == self.transport_stream_id and (
                    self.original_network_id is None or d.original_network_id == self.original_network_id):
                return d
        return None

    @property
    def orbital_positions(self) -> list[str]:
        return sorted({d.orbital_label for d in self.deliveries})

    def to_text(self) -> str:
        out = [f"packets: {self.packets}  sync errors: {self.sync_errors}  "
               f"continuity errors: {self.cc_errors}  bad CRC sections: {self.crc_errors}",
               f"transport_stream_id: {self.transport_stream_id}  original_network_id: "
               f"{self.original_network_id}  network: {self.network_name or '-'} ({self.network_id})"]
        here = self.this_transponder
        if here:
            out.append(f"this transponder: {here.frequency_khz / 1000:.3f} MHz {here.polarization} "
                       f"{here.symbol_rate // 1000} ksym/s {here.modulation_system} {here.modulation} "
                       f"FEC {here.fec} @ {here.orbital_label}")
        if self.orbital_positions:
            out.append("satellite position(s) announced in NIT: " + ", ".join(self.orbital_positions))
        else:
            out.append("satellite position: not announced (no NIT satellite delivery descriptor)")
        out.append(f"\nservices: {len(self.services)}")
        for s in sorted(self.services, key=lambda s: s.service_id):
            kind = self.service_types.get(s.service_id, "")
            flag = "  [scrambled]" if s.scrambled else ""
            out.append(f"  {s.service_id:>5}  {s.service_name or '(no SDT name)'}  {kind}{flag}")
            out.append(f"         PMT 0x{s.pmt_pid:04x}  PCR 0x{s.pcr_pid:04x}")
            for c in s.components:
                lang = f" [{c.language}]" if c.language else ""
                out.append(f"         {c.component_type:<8} PID 0x{c.pid:04x} ({c.pid})  {c.codec or ''}{lang}")
        if self.deliveries:
            out.append(f"\nNIT transponders: {len(self.deliveries)}")
            for d in sorted(self.deliveries, key=lambda d: (d.orbital_position, d.frequency_khz)):
                out.append(f"  {d.orbital_label:>7}  {d.frequency_khz / 1000:>10.3f} MHz {d.polarization}  "
                           f"{d.symbol_rate // 1000:>6} ksym/s  {d.modulation_system} {d.modulation} "
                           f"FEC {d.fec}  tsid {d.transport_stream_id}")
        busiest = sorted(self.pid_counts.items(), key=lambda kv: -kv[1])[:20]
        out.append("\nPIDs by packet count: " + ", ".join(f"0x{p:04x}:{n}" for p, n in busiest))
        return "\n".join(out)


# --------------------------------------------------------------------------- #
# parser
# --------------------------------------------------------------------------- #

class TSParser:
    """Incremental parser: feed() bytes as they arrive, then report()."""

    def __init__(self) -> None:
        self.r = StreamReport()
        self._buf: dict[int, bytearray] = {}
        self._cc: dict[int, int] = {}
        self._pmt_pids: dict[int, int] = {}       # pmt pid -> program number
        self._pmts: dict[int, tuple[int, int, list[PIDComponent], bool]] = {}
        self._sdt: dict[int, tuple[str | None, int | None, bool]] = {}
        self._carry = b""
        self._nit_pid = 0x10
        self._seen_sections: set[tuple] = set()

    # ---- packet layer
    def feed(self, data: bytes) -> None:
        data = self._carry + data
        i = 0
        n = len(data)
        while i + TS_PACKET <= n:
            if data[i] != SYNC:
                self.r.sync_errors += 1
                nxt = data.find(bytes([SYNC]), i + 1)
                if nxt < 0:
                    i = n
                    break
                i = nxt
                continue
            self._packet(data[i:i + TS_PACKET])
            i += TS_PACKET
        self._carry = data[i:]

    def _packet(self, p: bytes) -> None:
        self.r.packets += 1
        pid = ((p[1] & 0x1F) << 8) | p[2]
        self.r.pid_counts[pid] = self.r.pid_counts.get(pid, 0) + 1
        if pid == 0x1FFF:
            return
        pusi = bool(p[1] & 0x40)
        if p[3] & 0xC0:
            self.r.scrambled_pids.add(pid)
        afc = (p[3] >> 4) & 0x3
        cc = p[3] & 0x0F
        if afc & 1:
            last = self._cc.get(pid)
            if last is not None and cc != (last + 1) & 0x0F and cc != last:
                self.r.cc_errors += 1
            self._cc[pid] = cc
        if not afc & 1:
            return
        off = 4
        if afc & 2:
            off += 1 + p[4]
        if off >= TS_PACKET:
            return
        if pid in (0x00, 0x11, self._nit_pid) or pid in self._pmt_pids:
            self._section_payload(pid, p[off:], pusi)

    # ---- section layer
    def _section_payload(self, pid: int, payload: bytes, pusi: bool) -> None:
        if pusi:
            ptr = payload[0]
            if pid in self._buf:
                self._buf[pid] += payload[1:1 + ptr]
                self._drain(pid)
            self._buf[pid] = bytearray(payload[1 + ptr:])
        elif pid in self._buf:
            self._buf[pid] += payload
        else:
            return
        self._drain(pid)

    def _drain(self, pid: int) -> None:
        buf = self._buf.get(pid)
        while buf is not None and len(buf) >= 3:
            if buf[0] == 0xFF:
                del self._buf[pid]
                return
            total = 3 + (((buf[1] & 0x0F) << 8) | buf[2])
            if len(buf) < total:
                return
            section = bytes(buf[:total])
            del buf[:total]
            self._section(pid, section)

    def _section(self, pid: int, s: bytes) -> None:
        if len(s) < 12 or not s[1] & 0x80:
            return
        if crc32_mpeg2(s) != 0:
            self.r.crc_errors += 1
            return
        key = (pid, s[0], s[3], s[4], s[5] & 0x3E, s[6])
        if key in self._seen_sections:
            return
        self._seen_sections.add(key)
        table = s[0]
        if pid == 0x00 and table == 0x00:
            self._pat(s)
        elif pid in self._pmt_pids and table == 0x02:
            self._pmt(pid, s)
        elif pid == 0x11 and table == 0x42:
            self._sdt_section(s)
        elif pid == self._nit_pid and table in (0x40, 0x41):
            self._nit(s, actual=table == 0x40)

    def _pat(self, s: bytes) -> None:
        self.r.transport_stream_id = (s[3] << 8) | s[4]
        for i in range(8, len(s) - 4, 4):
            prog = (s[i] << 8) | s[i + 1]
            pid = ((s[i + 2] & 0x1F) << 8) | s[i + 3]
            if prog == 0:
                self._nit_pid = pid
            else:
                self._pmt_pids[pid] = prog

    def _pmt(self, pmt_pid: int, s: bytes) -> None:
        prog = (s[3] << 8) | s[4]
        pcr = ((s[8] & 0x1F) << 8) | s[9]
        pinfo = ((s[10] & 0x0F) << 8) | s[11]
        scrambled = any(tag == 0x09 for tag, _ in iter_descriptors(s[12:12 + pinfo]))
        comps: list[PIDComponent] = []
        i = 12 + pinfo
        end = len(s) - 4
        while i + 5 <= end:
            stype = s[i]
            pid = ((s[i + 1] & 0x1F) << 8) | s[i + 2]
            esl = ((s[i + 3] & 0x0F) << 8) | s[i + 4]
            descs = list(iter_descriptors(s[i + 5:i + 5 + esl]))
            i += 5 + esl
            comps.append(self._component(stype, pid, descs))
            if any(tag == 0x09 for tag, _ in descs):
                scrambled = True
        self._pmts[prog] = (pmt_pid, pcr, comps, scrambled)
        self._rebuild()

    @staticmethod
    def _component(stype: int, pid: int, descs: list[tuple[int, bytes]]) -> PIDComponent:
        tags = tuple(t for t, _ in descs)
        lang = None
        ctag = None
        for t, d in descs:
            if t == 0x0A and len(d) >= 3:
                lang = d[:3].decode("latin-1", "replace")
            elif t in (0x56, 0x59) and len(d) >= 3 and lang is None:
                lang = d[:3].decode("latin-1", "replace")
            elif t == 0x52 and d:
                ctag = d[0]
        if stype in VIDEO_STREAM_TYPES:
            return PIDComponent(pid, "video", VIDEO_STREAM_TYPES[stype], lang, ctag)
        for t, d in descs:
            if t == 0x7F and d and d[0] in AUDIO_EXTENSION_TAGS:
                return PIDComponent(pid, "audio", get_codec(AUDIO_EXTENSION_TAGS[d[0]]).name, lang, ctag)
        if stype in EXTRA_AUDIO_STREAM_TYPES:
            return PIDComponent(pid, "audio", get_codec(EXTRA_AUDIO_STREAM_TYPES[stype]).name, lang, ctag)
        codec = identify_audio_candidate(stype, tags)
        if codec:
            return PIDComponent(pid, "audio", codec.name, lang, ctag)
        if 0x59 in tags:
            return PIDComponent(pid, "subtitle", "DVB subtitles", lang, ctag)
        if 0x56 in tags:
            return PIDComponent(pid, "subtitle", "Teletext", lang, ctag)
        return PIDComponent(pid, "data", f"stream_type 0x{stype:02x}", lang, ctag)

    def _sdt_section(self, s: bytes) -> None:
        self.r.transport_stream_id = self.r.transport_stream_id or ((s[3] << 8) | s[4])
        self.r.original_network_id = (s[8] << 8) | s[9]
        i, end = 11, len(s) - 4
        while i + 5 <= end:
            sid = (s[i] << 8) | s[i + 1]
            free_ca = bool(s[i + 3] & 0x10)
            dl = ((s[i + 3] & 0x0F) << 8) | s[i + 4]
            name = stype = None
            for tag, d in iter_descriptors(s[i + 5:i + 5 + dl]):
                if tag == 0x48 and len(d) >= 3:
                    stype = d[0]
                    pl = d[1]
                    provider = dvb_text(d[2:2 + pl])
                    nl = d[2 + pl] if len(d) > 2 + pl else 0
                    name = dvb_text(d[3 + pl:3 + pl + nl])
                    if provider:
                        self.r.providers[sid] = provider
            i += 5 + dl
            self._sdt[sid] = (name, stype, free_ca)
            if stype is not None:
                self.r.service_types[sid] = SERVICE_TYPES.get(stype, f"type 0x{stype:02x}")
        self._rebuild()

    def _nit(self, s: bytes, actual: bool) -> None:
        if actual:
            self.r.network_id = (s[3] << 8) | s[4]
        ndl = ((s[8] & 0x0F) << 8) | s[9]
        for tag, d in iter_descriptors(s[10:10 + ndl]):
            if tag == 0x40 and actual:
                self.r.network_name = dvb_text(d)
        i = 10 + ndl
        tsl = ((s[i] & 0x0F) << 8) | s[i + 1]
        i += 2
        end = min(i + tsl, len(s) - 4)
        while i + 6 <= end:
            tsid = (s[i] << 8) | s[i + 1]
            onid = (s[i + 2] << 8) | s[i + 3]
            dl = ((s[i + 4] & 0x0F) << 8) | s[i + 5]
            for tag, d in iter_descriptors(s[i + 6:i + 6 + dl]):
                if tag == 0x43 and len(d) >= 11:
                    self.r.deliveries.append(parse_satellite_delivery(tsid, onid, d))
            i += 6 + dl

    def _rebuild(self) -> None:
        services = []
        for prog, (pmt_pid, pcr, comps, scr) in self._pmts.items():
            name, _stype, free_ca = self._sdt.get(prog, (None, None, False))
            pes_scrambled = any(c.pid in self.r.scrambled_pids for c in comps)
            services.append(ServiceRecord(prog, name, self.r.transport_stream_id, self.r.original_network_id,
                                          pmt_pid, pcr, tuple(comps), scr or free_ca or pes_scrambled))
        self.r.services = services

    def report(self) -> StreamReport:
        self._rebuild()
        return self.r


def parse_satellite_delivery(tsid: int, onid: int, d: bytes) -> SatelliteDelivery:
    freq = bcd(d[0:4], 8) * 10                     # units of 10 kHz -> kHz
    orbital = bcd(d[4:6], 4) / 10.0
    flags = d[6]
    s2 = bool(flags & 0x04)
    sr = bcd(d[7:11], 7) * 100                     # units of 100 sym/s
    return SatelliteDelivery(
        transport_stream_id=tsid, original_network_id=onid, frequency_khz=freq,
        orbital_position=orbital, east=bool(flags & 0x80),
        polarization=POLARIZATION[(flags >> 5) & 3],
        modulation_system="DVB-S2" if s2 else "DVB-S",
        modulation=SAT_MODULATION[flags & 3],
        roll_off=SAT_ROLLOFF[(flags >> 3) & 3] if s2 else None,
        symbol_rate=sr, fec=FEC_INNER.get(d[10] & 0x0F, "auto"))


def analyze_file(path: str, max_bytes: int | None = None, chunk: int = 1 << 20) -> StreamReport:
    parser = TSParser()
    read = 0
    with open(path, "rb") as f:
        while True:
            block = f.read(chunk)
            if not block:
                break
            parser.feed(block)
            read += len(block)
            if max_bytes and read >= max_bytes:
                break
    return parser.report()
