"""Band plans: what to sweep, how to convert to sky frequency, and which SDR reaches it.

Two kinds of reception:
* Direct: the antenna feeds the SDR at the real frequency (LOF 0). L-band,
  S-band and C-band up to 6 GHz with a HackRF One; L-band with RTL-SDRs.
* Through an LNB: a dish LNB converts the band down to the 950-2150 MHz IF
  (C-band, Ku-band, Ka-band). Sky frequency = LOF +/- IF.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BandPlan:
    name: str
    lof_mhz: float            # 0 = direct reception (no LNB)
    start_mhz: float          # SDR sweep range (IF when an LNB is used)
    stop_mhz: float
    bin_khz: int
    min_sr_ksym: int
    lnb: str | None           # dvbv5 LNB preset, if DVB tuning applies
    note: str

    @property
    def direct(self) -> bool:
        return self.lof_mhz == 0


BANDS: dict[str, BandPlan] = {p.name: p for p in (
    BandPlan("L-band direct 1-2 GHz", 0, 1000, 2000, 100, 2, None,
             "Patch, helix or dish feed plus an L-band LNA; no LNB. Inmarsat, Iridium, GNSS, HRPT weather."),
    BandPlan("L-band Inmarsat 1525-1559 MHz", 0, 1525, 1559, 10, 1, None,
             "Narrow carriers: small bins. Patch or helix antenna with LNA and filter."),
    BandPlan("S-band direct 2-4 GHz", 0, 2000, 4000, 250, 50, None,
             "HackRF One required (RTL-SDRs stop near 1.75-2.2 GHz). Helix or small dish feed with LNA."),
    BandPlan("C-band direct 3.4-4.2 GHz", 0, 3400, 4200, 250, 100, None,
             "HackRF One with a C-band feed and LNA (no LNB). Weaker than using a C-band LNB."),
    BandPlan("Wideband direct 1-6000 MHz", 0, 1, 6000, 1000, 100, None,
             "HackRF One only: survey everything it can reach, up to 6 GHz."),
    BandPlan("C-band LNB (LO 5150)", 5150, 950, 1450, 1000, 100, "C-BAND",
             "C-band LNBF with 5G filter; 3.7-4.2 GHz -> 950-1450 MHz IF (spectrum inverted)."),
    BandPlan("Ku-band low (LO 9750)", 9750, 950, 1950, 1000, 100, "UNIVERSAL",
             "Universal Ku LNB, 22 kHz off: 10.70-11.70 GHz."),
    BandPlan("Ku-band high (LO 10600)", 10600, 1100, 2150, 1000, 100, "UNIVERSAL",
             "Universal Ku LNB, 22 kHz on: 11.70-12.75 GHz."),
    BandPlan("Ka-band LNB (LO 18250)", 18250, 950, 2150, 1000, 100, None,
             "Ka LNB with an 18.25 GHz LO: 19.20-20.40 GHz. Check your LNB label; many Ka LNBs select the LO by voltage/tone."),
    BandPlan("Ka-band LNB (LO 19250)", 19250, 950, 2150, 1000, 100, None,
             "Ka LNB with a 19.25 GHz LO: 20.20-21.40 GHz."),
    BandPlan("Ka-band LNB (LO 20250)", 20250, 950, 2150, 1000, 100, None,
             "Ka LNB with a 20.25 GHz LO: 21.20-22.40 GHz."),
    BandPlan("Custom", 0, 950, 2150, 1000, 100, None, "Enter your own LOF and sweep range."),
)}

# Receiver tuning ranges in MHz (approximate, per tuner chip).
SDRS: dict[str, tuple[str, float, float, str]] = {
    "RTL-SDR E4000 (e.g. NESDR SMArTee XTR)": ("rtl_power", 52, 2200,
                                               "E4000 tuners usually have a gap near 1100-1250 MHz."),
    "RTL-SDR R820T2 / R828D (e.g. NESDR Nano 3, RTL-SDR Blog V3/V4)": ("rtl_power", 24, 1766, ""),
    "HackRF One": ("hackrf_sweep", 1, 6000, ""),
    "No SDR yet (simulated test signal)": ("Simulated test signal", 1, 6000, ""),
}


def sweep_range(plan: BandPlan, sdr: str) -> tuple[float, float, str]:
    """Clip the plan's sweep to what the SDR can reach. Returns (start, stop, warning)."""
    _tool, lo, hi, quirk = SDRS.get(sdr, SDRS["HackRF One"])
    start, stop = max(plan.start_mhz, lo), min(plan.stop_mhz, hi)
    if start >= stop:
        return plan.start_mhz, plan.stop_mhz, (f"{sdr.split(' (')[0]} cannot reach {plan.start_mhz:g}-"
                                               f"{plan.stop_mhz:g} MHz (range {lo:g}-{hi:g} MHz). Use a HackRF One.")
    warn = ""
    if start > plan.start_mhz or stop < plan.stop_mhz:
        warn = f"Sweep limited to {start:g}-{stop:g} MHz by the receiver's range."
    if quirk and start < 1250 and stop > 1100:
        warn = (warn + " " + quirk).strip()
    return start, stop, warn
