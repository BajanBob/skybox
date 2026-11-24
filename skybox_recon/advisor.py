"""Cognitive receiver advisor: learns from scan history, recommends actions,
identifies satellites from NIT data or a user-supplied transponder list, and
runs an automatic acquisition plan (sweep -> detect -> tune -> parse PIDs).

Rule-based and fully local: no network, no external AI service.
"""
from __future__ import annotations

import csv
import json
import os
import time
from dataclasses import asdict, dataclass

from .dvb import IF_MAX_MHZ, IF_MIN_MHZ
from .spectrum import Transponder


def data_dir() -> str:
    base = os.environ.get("APPDATA") or os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")
    path = os.path.join(base, "SkyboxRecon")
    os.makedirs(path, exist_ok=True)
    return path


@dataclass
class Advice:
    level: str      # info, action, warning
    text: str

    def __str__(self) -> str:
        return f"[{self.level.upper()}] {self.text}"


@dataclass
class RefTransponder:
    satellite: str
    orbital: str
    freq_mhz: float
    pol: str
    sr_ksym: int


def load_reference(path: str) -> list[RefTransponder]:
    """CSV with header: satellite,orbital,freq_mhz,pol,sr_ksym (one row per transponder)."""
    out = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                out.append(RefTransponder(row["satellite"].strip(), row["orbital"].strip(),
                                          float(row["freq_mhz"]), row["pol"].strip().upper()[:1],
                                          int(float(row["sr_ksym"]))))
            except (KeyError, ValueError):
                continue
    return out


def identify_satellite(found: list[Transponder], reference: list[RefTransponder],
                       freq_tol_mhz: float = 4.0, sr_tol: float = 0.15) -> list[tuple[str, str, float, int]]:
    """Rank satellites by the share of detected carriers matching their list.

    Returns (satellite, orbital, confidence 0..1, matches). A confidence, never
    a certainty: unknown signals alone do not prove an orbital position.
    """
    by_sat: dict[tuple[str, str], list[RefTransponder]] = {}
    for r in reference:
        by_sat.setdefault((r.satellite, r.orbital), []).append(r)
    ranked = []
    for (sat, orb), refs in by_sat.items():
        hits = 0
        for t in found:
            if any(abs(t.rf_mhz - r.freq_mhz) <= freq_tol_mhz and (t.pol in ("?", r.pol))
                   and abs(t.sr_ksym - r.sr_ksym) <= max(1000, sr_tol * r.sr_ksym) for r in refs):
                hits += 1
        if hits:
            conf = hits / max(len(found), 1) * min(1.0, hits / 3)
            ranked.append((sat, orb, round(conf, 2), hits))
    return sorted(ranked, key=lambda r: (-r[2], -r[3]))


class CognitiveAdvisor:
    def __init__(self, history_path: str | None = None) -> None:
        self.path = history_path or os.path.join(data_dir(), "scan-history.json")
        try:
            with open(self.path, encoding="utf-8") as f:
                self.history: list[dict] = json.load(f)
        except (OSError, ValueError):
            self.history = []

    def record(self, found: list[Transponder], lof_mhz: float, pol: str, floor_db: float) -> None:
        self.history.append({"time": time.time(), "lof": lof_mhz, "pol": pol, "floor": floor_db,
                             "carriers": [asdict(t) for t in found]})
        self.history = self.history[-200:]
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.history, f)
        except OSError:
            pass

    def previous(self, pol: str, lof_mhz: float) -> dict | None:
        for h in reversed(self.history[:-1]):
            if h.get("pol") == pol and h.get("lof") == lof_mhz:
                return h
        return None

    def advise(self, found: list[Transponder], floor_db: float, lof_mhz: float, pol: str,
               nit_positions: list[str] | None = None,
               reference_matches: list[tuple[str, str, float, int]] | None = None) -> list[Advice]:
        tips: list[Advice] = []
        if not found:
            tips.append(Advice("warning", "No carriers above the noise floor. Check LNB power "
                               "(13 V vertical / 18 V horizontal from a receiver or power inserter), "
                               "the cable and the LNB LOF; the dish may be off target."))
            if floor_db < -100:
                tips.append(Advice("warning", "Noise floor is very low: the LNB is probably not powered."))
            return tips
        best = max(found, key=lambda t: t.snr_db)
        tips.append(Advice("action", f"Strongest carrier: {best.rf_mhz:.0f} MHz {best.pol}, "
                           f"~{best.sr_ksym} ksym/s, C/N {best.snr_db:.1f} dB. Tune this first."))
        if best.snr_db < 6:
            tips.append(Advice("action", "All carriers are weak (C/N under 6 dB). Peak the dish with the "
                               "finder tone: small azimuth steps, then elevation, then LNB skew."))
        elif best.snr_db < 10:
            tips.append(Advice("info", "Signal is usable but marginal; a small azimuth or skew "
                               "adjustment may gain 2-4 dB."))
        prev = self.previous(pol, lof_mhz)
        if prev and prev.get("carriers"):
            prev_best = max(c["snr_db"] for c in prev["carriers"])
            delta = best.snr_db - prev_best
            if abs(delta) >= 1:
                tips.append(Advice("info", f"Best C/N {'up' if delta > 0 else 'down'} {abs(delta):.1f} dB "
                                   f"since the last {pol} scan ({len(prev['carriers'])} -> {len(found)} carriers)."))
        edge = [t for t in found if t.if_mhz < IF_MIN_MHZ + 10 or t.if_mhz > IF_MAX_MHZ - 10]
        if edge:
            tips.append(Advice("info", f"{len(edge)} carrier(s) at the edge of the IF band may be cut off; "
                               "try the other LNB band (22 kHz tone on/off)."))
        narrow = [t for t in found if t.sr_ksym < 2000]
        if narrow:
            tips.append(Advice("action", f"{len(narrow)} narrow carrier(s) under 2 Msym/s: use the SDR "
                               "low-symbol-rate path (leandvb) and the Constellation tab."))
        wide = [t for t in found if t.sr_ksym > 45000]
        if wide:
            tips.append(Advice("info", f"{len(wide)} very wide carrier(s): may be two adjacent transponders; "
                               "rescan with finer bins."))
        if nit_positions:
            tips.append(Advice("info", "Satellite identified from the broadcast NIT: " + ", ".join(nit_positions)))
        elif reference_matches:
            sat, orb, conf, hits = reference_matches[0]
            tips.append(Advice("info", f"Carrier pattern matches {sat} ({orb}) with confidence "
                               f"{conf:.0%} ({hits} carriers). Confirm by tuning and reading the NIT."))
        else:
            tips.append(Advice("info", "Satellite not yet identified: tune a carrier and run Services/PIDs "
                               "to read the NIT, or load a transponder list for pattern matching."))
        return tips


@dataclass
class PlanStep:
    name: str
    status: str = "pending"   # pending, running, done, skipped, failed
    detail: str = ""


def acquisition_plan(have_sdr: bool, have_dvb: bool) -> list[PlanStep]:
    """The automatic acquisition sequence the GUI's Auto-acquire button runs."""
    return [
        PlanStep("Sweep 950-2150 MHz", "pending" if have_sdr else "skipped",
                 "" if have_sdr else "no rtl_power / hackrf_sweep found"),
        PlanStep("Detect carriers and estimate symbol rates", "pending" if have_sdr else "skipped"),
        PlanStep("Rank carriers and advise", "pending" if have_sdr else "skipped"),
        PlanStep("Tune the strongest carrier (dvbv5-zap)", "pending" if have_dvb else "skipped",
                 "" if have_dvb else "needs a Linux DVB-S2 adapter and dvbv5-zap"),
        PlanStep("Record 10 s of transport stream", "pending" if have_dvb else "skipped"),
        PlanStep("Parse PAT/PMT/SDT/NIT: services, PIDs, satellite", "pending" if have_dvb else "skipped"),
    ]
