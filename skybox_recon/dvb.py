"""DVB-S / S2 / S2X parameters, LNB arithmetic and dvbv5 channel files."""
from __future__ import annotations

from dataclasses import dataclass

# Standard-defined modulation families (EN 300 421, EN 302 307-1/-2).
MODULATIONS = {
    "DVBS": ("QPSK",),
    "DVBS2": ("QPSK", "8PSK", "16APSK", "32APSK"),
    "DVBS2X": ("QPSK", "8PSK", "8APSK-L", "16APSK", "16APSK-L", "32APSK", "32APSK-L",
               "64APSK", "64APSK-L", "128APSK", "256APSK", "256APSK-L", "pi/2-BPSK"),
}
ALL_MODULATIONS = ("auto",) + tuple(dict.fromkeys(m for ms in MODULATIONS.values() for m in ms))

# libdvbv5 channel-file spellings for modulations the Linux DVB API names.
# Others are written as QAM/AUTO so the demodulator detects them, with the
# requested mode kept in a comment.
DVBV5_MODULATION = {"auto": "QAM/AUTO", "QPSK": "QPSK", "8PSK": "PSK/8",
                    "16APSK": "APSK/16", "32APSK": "APSK/32"}
FEC = ("auto", "1/4", "1/3", "2/5", "1/2", "3/5", "2/3", "3/4", "4/5", "5/6", "7/8", "8/9", "9/10", "none")
DVBV5_FEC = {"auto": "AUTO", "none": "NONE"}
DVBV5_POL = {"H": "HORIZONTAL", "V": "VERTICAL", "L": "LEFT", "R": "RIGHT"}
ROLLOFF = ("auto", "0.35", "0.25", "0.20", "0.15", "0.10", "0.05")
DVBV5_ROLLOFF = {"auto": "AUTO", "0.35": "35", "0.25": "25", "0.20": "20",
                 "0.15": "15", "0.10": "10", "0.05": "5"}
PILOT = ("auto", "on", "off")
INVERSION = ("auto", "on", "off")
PLS_MODES = ("ROOT", "GOLD", "COMBO")

# LNB presets understood by dvbv5-zap -l (local oscillator frequencies in MHz).
LNBS = {
    "UNIVERSAL": {"lof_low": 9750, "lof_high": 10600, "switch": 11700},
    "ENHANCED": {"lof_low": 9750},
    "STANDARD": {"lof_low": 10000},
    "L10700": {"lof_low": 10700},
    "L10750": {"lof_low": 10750},
    "L11300": {"lof_low": 11300},
    "DBS": {"lof_low": 11250},
    "C-BAND": {"lof_low": 5150},
}

IF_MIN_MHZ, IF_MAX_MHZ = 950.0, 2150.0


def if_to_rf(if_mhz: float, lof_mhz: float) -> float:
    """C-band LNBs (LOF below the signal) invert the spectrum: RF = LOF - IF."""
    return lof_mhz - if_mhz if lof_mhz < 6000 else lof_mhz + if_mhz


def rf_to_if(rf_mhz: float, lof_mhz: float) -> float:
    return lof_mhz - rf_mhz if lof_mhz < 6000 else rf_mhz - lof_mhz


def lnb_for(rf_mhz: float, lnb: str = "UNIVERSAL") -> tuple[float, bool]:
    """Return (LOF MHz, 22 kHz tone on) for an RF frequency and LNB preset."""
    p = LNBS[lnb]
    if "lof_high" in p and rf_mhz >= p["switch"]:
        return float(p["lof_high"]), True
    return float(p["lof_low"]), False


def voltage_for(pol: str) -> int:
    """13 V selects vertical / right-hand, 18 V horizontal / left-hand."""
    return 18 if pol in ("H", "L") else 13


def stream_id(isi: int | None, pls_code: int | None, pls_mode: str = "ROOT") -> int | None:
    """Linux DTV_STREAM_ID packing: ISI bits 0-7, PLS code 8-25, PLS mode 26-27."""
    if isi is None and pls_code is None:
        return None
    return ((PLS_MODES.index(pls_mode) & 3) << 26) | (((pls_code or 0) & 0x3FFFF) << 8) | ((isi or 0) & 0xFF)


@dataclass
class TuneParams:
    freq_khz: int                 # RF frequency in kHz (what dvbv5 expects for satellite)
    sr: int                       # symbols/s
    delsys: str = "DVBS2"
    mod: str = "auto"
    fec: str = "auto"
    pol: str = "H"
    rolloff: str = "auto"
    pilot: str = "auto"
    inversion: str = "auto"
    isi: int | None = None
    pls_code: int | None = None
    pls_mode: str = "ROOT"
    sat_number: int | None = None  # DiSEqC port (0-3)
    service: str = "ch1"

    def validate(self) -> None:
        if self.delsys not in MODULATIONS:
            raise ValueError(f"standard must be one of {', '.join(MODULATIONS)}")
        if self.mod != "auto" and self.mod not in MODULATIONS[self.delsys]:
            raise ValueError(f"{self.mod} is not a {self.delsys} modulation")
        if self.sr <= 0 or self.freq_khz <= 0:
            raise ValueError("frequency and symbol rate must be positive")
        if self.pol not in DVBV5_POL:
            raise ValueError("polarization must be H, V, L or R")


def dvbv5_conf(p: TuneParams) -> str:
    p.validate()
    mod = DVBV5_MODULATION.get(p.mod, "QAM/AUTO")
    lines = [f"[{p.service}]",
             f"\tDELIVERY_SYSTEM = {p.delsys}",
             f"\tFREQUENCY = {p.freq_khz}",
             f"\tSYMBOL_RATE = {p.sr}",
             f"\tINNER_FEC = {DVBV5_FEC.get(p.fec, p.fec)}",
             f"\tMODULATION = {mod}",
             f"\tPOLARIZATION = {DVBV5_POL[p.pol]}",
             f"\tINVERSION = {p.inversion.upper()}"]
    if p.delsys != "DVBS":
        lines += [f"\tROLLOFF = {DVBV5_ROLLOFF.get(p.rolloff, 'AUTO')}", f"\tPILOT = {p.pilot.upper()}"]
    sid = stream_id(p.isi, p.pls_code, p.pls_mode)
    if sid is not None:
        lines.append(f"\tSTREAM_ID = {sid}")
    if p.sat_number is not None:
        lines.append(f"\tSAT_NUMBER = {p.sat_number}")
    head = ""
    if p.mod not in DVBV5_MODULATION:
        head = f"# requested modulation {p.mod}: written as QAM/AUTO (demodulator detects it)\n"
    return head + "\n".join(lines) + "\n"


def dvbv5_zap_cmd(conf_path: str, p: TuneParams, adapter: int = 0, frontend: int = 0,
                  lnb: str = "UNIVERSAL", out: str = "pipe:1", seconds: int = 600) -> list[str]:
    cmd = ["dvbv5-zap", "-a", str(adapter), "-f", str(frontend), "-l", lnb, "-c", conf_path,
           "-t", str(seconds)]
    if p.sat_number is not None:
        cmd += ["-S", str(p.sat_number)]
    if out:
        cmd += ["-o", out]
    return cmd + [p.service]


def list_dvb_adapters(root: str = "/dev/dvb") -> list[int]:
    """Linux DVB adapters present (empty elsewhere)."""
    import os
    try:
        return sorted(int(n[7:]) for n in os.listdir(root) if n.startswith("adapter") and n[7:].isdigit())
    except OSError:
        return []
