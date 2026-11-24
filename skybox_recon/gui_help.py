"""Hover help tips and the first-run setup wizard for the desktop app."""
from __future__ import annotations

import json
import os
import shutil
import tkinter as tk
from tkinter import ttk

from .advisor import data_dir

# --------------------------------------------------------------------------- #
# settings
# --------------------------------------------------------------------------- #

SETTINGS = os.path.join(data_dir(), "settings.json")

from .bands import BANDS as BAND_PLANS
from .bands import SDRS as TUNERS

BANDS = {name: (f"{p.lof_mhz:g}", p.lnb or "UNIVERSAL") for name, p in BAND_PLANS.items() if name != "Custom"}


def load_settings() -> dict | None:
    try:
        with open(SETTINGS, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def save_settings(data: dict) -> None:
    try:
        with open(SETTINGS, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except OSError:
        pass


# --------------------------------------------------------------------------- #
# hover tips
# --------------------------------------------------------------------------- #

class Tooltip:
    DELAY_MS = 450

    def __init__(self, widget: tk.Widget, text: str) -> None:
        self.widget, self.text = widget, text
        self.win: tk.Toplevel | None = None
        self.job = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _e=None):
        self._cancel()
        self.job = self.widget.after(self.DELAY_MS, self._show)

    def _cancel(self):
        if self.job:
            self.widget.after_cancel(self.job)
            self.job = None

    def _show(self):
        if self.win or not self.widget.winfo_viewable():
            return
        x = self.widget.winfo_rootx() + 12
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        self.win = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        try:
            tw.attributes("-topmost", True)
        except tk.TclError:
            pass
        tk.Label(tw, text=self.text, justify="left", wraplength=340, bg="#fff8dc", fg="#1b2432",
                 relief="solid", borderwidth=1, padx=8, pady=6, font=("Segoe UI", 9)).pack()

    def _hide(self, _e=None):
        self._cancel()
        if self.win:
            self.win.destroy()
            self.win = None


# Tips keyed by the label or button text they belong to.
TIPS = {
    # spectrum
    "Source": "Where the spectrum comes from: rtl_power (RTL-SDR), hackrf_sweep (HackRF One), a saved CSV "
              "sweep, or the built-in simulated test signal.",
    "LNB LOF (MHz)": "LNB local-oscillator frequency. Universal Ku: 9750 (low band) or 10600 (high band, "
                     "22 kHz on). C-band: 5150. Used to show real sky frequencies.",
    "Polarization (LNB 18 V = H)": "Which polarization the LNB is set to. 18 V selects horizontal (or left-hand), "
                                   "13 V selects vertical (or right-hand). Set it to match your power inserter.",
    "Gain (dB)": "SDR gain. Start around 20-30. Lower it (or add a 6-10 dB attenuator) if the noise floor "
                 "rises and carriers look flattened.",
    "Bin (kHz)": "Width of each spectrum point. 1000 kHz is quick; 250-500 kHz gives sharper symbol-rate "
                 "estimates but sweeps more slowly.",
    "Tuner": "Your SDR model limits the sweep: R820T2/R828D dongles reach about 1766 MHz, E4000 about 2200 MHz "
             "(with a gap near 1100-1250 MHz), HackRF One 1-6000 MHz.",
    "Band": "Band plan: direct L/S/C-band reception up to 6 GHz, or C, Ku and Ka bands through a dish LNB. "
            "Sets the LOF, sweep range and bin width.",
    "LNB LOF (MHz, 0 = direct)": "LNB local oscillator. 0 means no LNB (antenna straight into the SDR). C-band 5150, "
                                 "Ku 9750/10600, Ka typically 18250-21200: check your LNB label.",
    "Sweep start (MHz)": "Lowest frequency the SDR sweeps (IF when an LNB is used).",
    "Sweep stop (MHz)": "Highest frequency the SDR sweeps. Clipped to what your SDR can reach.",
    "Start": "Begin sweeping. The trace, waterfall and finder update with every sweep.",
    "Stop": "Stop the current sweep or job.",
    "Beep": "Audible finder: higher and faster beeps as signal improves, steady tone at lock level.",
    "Reset peak": "Clear the peak-hold reading, e.g. before re-aiming the dish.",
    # blind scan
    "Threshold (dB over floor)": "How far a carrier must rise above the noise floor to count. 3 dB finds weak "
                                 "carriers; 6 dB lists only strong ones.",
    "Min SR (ksym/s)": "Ignore carriers narrower than this symbol rate.",
    "Max SR (ksym/s)": "Ignore carriers wider than this symbol rate.",
    "Scan latest sweep": "Find every carrier in the most recent sweep and estimate its symbol rate.",
    "Send to Tuning": "Copy the selected carrier's frequency, symbol rate and polarization to the Tuning tab.",
    "Load transponder list…": "Load a CSV (satellite,orbital,freq_mhz,pol,sr_ksym) to identify the satellite "
                              "by matching the carrier pattern.",
    # constellation
    "IQ file (.cu8 rtl_sdr, .cs8 hackrf, .cf32)": "A raw IQ capture. rtl_sdr writes .cu8, hackrf_transfer "
                                                   "writes .cs8, GNU Radio and SDR# write .cf32.",
    "Sample rate (S/s)": "The capture's sample rate. It must be higher than the symbol rate.",
    "Symbol rate": "The carrier's symbol rate in symbols per second (from Blind Scan).",
    "Modulation": "Modulation to demodulate or tune.",
    "Roll-off": "Pulse-shaping roll-off. DVB-S uses 0.35; DVB-S2 also 0.25 or 0.20.",
    "Analyze file": "Recover the constellation and measure MER from the chosen IQ file.",
    "Capture 2 s and analyze": "Record 2 seconds with the selected SDR at the IF shown, then analyse it.",
    "Simulated QPSK": "Show a labelled simulated QPSK carrier to see what a good constellation looks like.",
    # services
    "Open .ts recording…": "Open a transport-stream recording (.ts) to list services, PIDs, codecs and the "
                           "satellite position announced in the NIT.",
    "Simulated stream": "Load a labelled simulated stream to see how results are shown.",
    # tuning
    "RF frequency (MHz)": "The transponder's real (sky) frequency, e.g. 11778.0 MHz for Ku or 4000.0 MHz for C-band.",
    "Symbol rate (sym/s)": "Transponder symbol rate, e.g. 27500000.",
    "Standard": "DVBS, DVBS2 or DVBS2X. S2X adds 8APSK-L to 256APSK and pi/2-BPSK.",
    "FEC": "Forward error correction rate. Leave on auto unless you know it.",
    "Pilot": "DVB-S2 pilot symbols. Leave on auto unless you know it.",
    "Spectral inversion": "Leave on auto. C-band LNBs invert the spectrum; the demodulator usually handles it.",
    "LNB": "LNB preset passed to dvbv5-zap (-l). UNIVERSAL switches 9750/10600 MHz at 11700 MHz; C-BAND is 5150 MHz.",
    "Stream ID / MIS": "Input stream ID for multistream transponders. Leave blank if not used.",
    "PLS code": "Physical-layer scrambling code for S2/S2X multistream. Leave blank if not used.",
    "PLS mode": "Physical-layer scrambling mode: ROOT, GOLD or COMBO.",
    "DiSEqC port": "Which input of a DiSEqC 1.0 switch to select (0-3), e.g. 0 = C-band LNB, 1 = Ku-band LNB.",
    "Service name": "Name used for the channel file and recording.",
    "Build channel file and command": "Write the dvbv5 channel file and the dvbv5-zap command for a Linux DVB-S2 tuner.",
    "Polarization": "H or V for linear LNBs (18 V = H, 13 V = V); L or R for circular.",
    "Adapter": "Linux DVB adapter number (/dev/dvb/adapterN) for this tuner.",
    "RF MHz": "Transponder sky frequency in MHz.",
    "SR": "Symbol rate in symbols per second.",
    "Pol": "Polarization: H (18 V) or V (13 V).",
    "Task": "What this tuner is doing, e.g. live view, recording, scanning.",
    "Watch window (IF MHz, blank = full band)": "Limit the finder to one carrier: enter its IF start and end in MHz.",
    # dual tuner / stream / advisor
    "Tune": "Tune this tuner with the settings shown and start recording its transport stream.",
    "I confirm the two adapters have separate RF inputs": "Two tuners need two separate dish cables (or a "
        "dual-output LNB). One tuner cannot be split in software.",
    "Source .ts": "The recording to stream. With 'Follow live recording' it streams a file a tuner is still writing.",
    "Port": "Network port for the stream (default 8090). Players open http://<this PC>:<port>/stream.ts.",
    "Follow live recording": "Keep streaming new data as a tuner writes the file, instead of looping it.",
    "Start streaming": "Serve the stream on your local network. No internet connection is used.",
    "Auto-acquire": "Sweep, detect carriers, tune the strongest, record 10 s and identify services and the "
                    "satellite. Steps needing hardware you don't have are skipped and explained.",
    # general
    "Setup wizard": "Step-by-step setup: band, SDR, LNB power and a first test.",
    "Open application folder": "Open the folder SkyboxRecon is installed in. Put rtl_power.exe or "
                               "hackrf_sweep.exe here if they are not on your PATH.",
    "Run self-test": "Offline checks of every engine. No hardware needed.",
    "Clear log": "Clear the diagnostics log.",
    "Browse…": "Choose a file.",
    "Analyze image": "Read-only firmware analysis: hashes, entropy map, signatures, partition records.",
    "Probe UART": "Find the receiver's serial console baud rate. Use a 3.3 V USB-TTL adapter; power-cycle "
                  "the receiver after starting.",
    "Refresh": "Re-list serial ports. Ports are also detected automatically every few seconds.",
    "Detect devices": "Scan USB now for SDRs (RTL-SDR, HackRF, bladeRF, Airspy, SDRplay) and USB-serial "
                      "adapters (CP210x, CH340, FTDI, PL2303, ESP32). The app also checks every 3 seconds and "
                      "picks the tuner and serial port for you. It warns if Windows still needs the Zadig driver.",
    "Setup wizard": "Step-by-step setup: band, SDR (auto-detected), LNB power, wiring checks and a first test.",
    "Open application folder": "Open the folder that holds the program, tools and your settings.",
    "Open": "Open this tool.",
}


def attach_tips(root: tk.Misc) -> int:
    """Walk the widget tree and attach a tip to every labelled control we know."""
    count = 0

    def visit(w):
        nonlocal count
        text = None
        try:
            if isinstance(w, (ttk.Button, ttk.Checkbutton, tk.Button)):
                text = w.cget("text")
            elif isinstance(w, (ttk.Entry, ttk.Combobox)):
                parent = w.master
                labels = [c for c in parent.winfo_children() if isinstance(c, (ttk.Label, tk.Label))]
                if labels:
                    text = labels[0].cget("text")
        except tk.TclError:
            pass
        if text and str(text) in TIPS and not getattr(w, "_skybox_tip", None):
            w._skybox_tip = Tooltip(w, TIPS[str(text)])
            count += 1
        for c in w.winfo_children():
            visit(c)

    visit(root)
    return count


# --------------------------------------------------------------------------- #
# setup wizard
# --------------------------------------------------------------------------- #

class SetupWizard(tk.Toplevel):
    def __init__(self, app) -> None:
        super().__init__(app)
        self.app = app
        self.title("Skybox Recon setup")
        self.configure(bg="#101a2b")
        self.geometry("680x520")
        self.minsize(600, 480)
        self.transient(app)
        prev = load_settings() or {}
        self.band = tk.StringVar(value=prev.get("band") if prev.get("band") in BANDS else "Ku-band low (LO 9750)")
        self.tuner = tk.StringVar(value=prev.get("tuner") if prev.get("tuner") in TUNERS else next(iter(TUNERS)))
        self.power = tk.StringVar(value=prev.get("power", "Fixed 18 V inserter (horizontal)"))
        self.checks = [tk.BooleanVar(value=False) for _ in range(4)]
        self.step = 0
        self.body = ttk.Frame(self, padding=20)
        self.body.pack(fill="both", expand=True)
        nav = ttk.Frame(self, padding=(20, 0, 20, 16))
        nav.pack(fill="x", side="bottom")
        self.progress = ttk.Label(nav, style="Sub.TLabel")
        self.progress.pack(side="left")
        self.next_btn = ttk.Button(nav, text="Next", style="Accent.TButton", command=self.next)
        self.next_btn.pack(side="right")
        self.back_btn = ttk.Button(nav, text="Back", command=self.back)
        self.back_btn.pack(side="right", padx=8)
        ttk.Button(nav, text="Skip", command=self.destroy).pack(side="right", padx=8)
        self.steps = [self.s_welcome, self.s_band, self.s_sdr, self.s_power, self.s_connect, self.s_test]
        self.render()

    # ---- frame helpers
    def clear(self, title, sub):
        for w in self.body.winfo_children():
            w.destroy()
        ttk.Label(self.body, text=title, style="Title.TLabel").pack(anchor="w")
        ttk.Label(self.body, text=sub, style="Sub.TLabel", wraplength=620, justify="left").pack(anchor="w", pady=(4, 14))

    def radio(self, var, options):
        for opt in options:
            ttk.Radiobutton(self.body, text=opt, value=opt, variable=var).pack(anchor="w", pady=3)

    def render(self):
        self.steps[self.step]()
        self.progress.config(text=f"Step {self.step + 1} of {len(self.steps)}")
        self.back_btn.state(["disabled"] if self.step == 0 else ["!disabled"])
        self.next_btn.config(text="Finish" if self.step == len(self.steps) - 1 else "Next")
        attach_tips(self)

    def next(self):
        if self.step == len(self.steps) - 1:
            self.finish()
            return
        self.step += 1
        self.render()

    def back(self):
        self.step = max(0, self.step - 1)
        self.render()

    # ---- steps
    def s_welcome(self):
        self.clear("Welcome to Skybox Recon",
                   "This wizard sets up the app for your dish and receiver in about two minutes. "
                   "You can rerun it any time from the Setup wizard button. Nothing here changes your hardware.")
        for line in ("1. Choose the satellite band.", "2. Tell us which SDR you have.",
                     "3. Choose how the LNB is powered.", "4. Check the wiring and safety points.",
                     "5. Run a first test."):
            ttk.Label(self.body, text=line).pack(anchor="w", pady=2)

    def s_band(self):
        self.clear("Which band?",
                   "Direct bands (L, S, C up to 6 GHz) use an antenna and LNA straight into the SDR; above about "
                   "2 GHz this needs a HackRF One. C, Ku and Ka bands through a dish use an LNB. Pick one to start with.")
        self.radio(self.band, list(BANDS))

    def s_sdr(self):
        self.clear("Which SDR is connected?",
                   "R820T2/R828D dongles reach about 1766 MHz, E4000 about 2200 MHz, HackRF One up to 6000 MHz. "
                   "The sweep is clipped to what your SDR can reach.")
        from . import devices as dv
        found = list(getattr(self.app, "devices", []) or [])
        sdr = dv.best_sdr(found)
        if sdr and sdr.sdr_key and not sdr.problem:
            self.tuner.set(sdr.sdr_key)
        self.radio(self.tuner, list(TUNERS))
        det = ttk.Frame(self.body)
        det.pack(anchor="w", pady=(12, 0))
        ttk.Label(det, text="Detected on USB:", style="Sub.TLabel").pack(anchor="w")
        if found:
            for d in found:
                ok = not d.problem
                ttk.Label(det, text=f"{'✓' if ok else '⚠'}  {d.label()}", wraplength=620, justify="left",
                          foreground="#3ccf91" if ok else "#f5c451").pack(anchor="w")
        else:
            ttk.Label(det, text="✗  Nothing yet — plug in the SDR, wait a few seconds, then press Detect devices.",
                      foreground="#f5c451").pack(anchor="w")
        ttk.Button(det, text="Detect devices", command=self._redetect).pack(anchor="w", pady=4)
        st = ttk.Frame(self.body)
        st.pack(anchor="w", pady=(14, 0))
        for tool in ("rtl_power", "hackrf_sweep"):
            ok = shutil.which(tool) is not None
            ttk.Label(st, text=f"{'✓' if ok else '✗'}  {tool} {'found' if ok else 'not found'}",
                      foreground="#3ccf91" if ok else "#f5c451").pack(anchor="w")
        ttk.Label(self.body, style="Sub.TLabel", wraplength=620, justify="left",
                  text="Not found? Install the RTL-SDR or HackRF tools and put rtl_power / hackrf_sweep on your PATH "
                       "or in the application folder. On Windows, set the RTL-SDR driver to WinUSB once with Zadig."
                  ).pack(anchor="w", pady=(8, 0))

    def _redetect(self):
        from . import devices as dv
        self.app.devices = dv.detect(probe_tuner=True)
        self.render()

    def s_power(self):
        self.clear("How is the LNB powered?",
                   "The LNB needs 13 V (vertical) or 18 V (horizontal), and 22 kHz for the Ku high band. "
                   "An SDR cannot supply this.")
        self.radio(self.power, ["Fixed 18 V inserter (horizontal)", "Fixed 13 V inserter (vertical)",
                                "Switchable 13/18 V + 22 kHz inserter", "Satellite receiver through a DC-pass splitter"])

    def s_connect(self):
        self.clear("Connect and check",
                   "Wire it with the inserter switched off: dish → inserter (LNB port) → inserter (receiver port) "
                   "→ DC block → attenuator → F-to-SMA → SDR → USB. Tick each point.")
        items = ["A DC block sits between the inserter and the SDR (13-18 V would damage the SDR).",
                 "The inserter was off while connecting cables.",
                 "A 6-10 dB attenuator is ready in case the SDR overloads.",
                 "For serial work: the USB-TTL adapter is 3.3 V and its VCC pin is not connected."]
        for var, text in zip(self.checks, items):
            ttk.Checkbutton(self.body, text=text, variable=var).pack(anchor="w", pady=4)

    def s_test(self):
        self.clear("First test",
                   "Finish applies your settings to the Spectrum, Blind Scan and Tuning tabs and opens the Spectrum "
                   "tab. Press Start there and turn on Beep to aim the dish.")
        row = ttk.Frame(self.body)
        row.pack(anchor="w", pady=6)
        ttk.Button(row, text="Run self-test", command=lambda: self.app.run_cli(["selftest"], "Self-test")).pack(side="left")
        self.summary = ttk.Label(self.body, style="Sub.TLabel", wraplength=620, justify="left")
        self.summary.pack(anchor="w", pady=10)
        lof, lnb = BANDS[self.band.get()]
        from .bands import sweep_range
        lo, hi, warn = sweep_range(BAND_PLANS[self.band.get()], self.tuner.get())
        tool = TUNERS[self.tuner.get()][0]
        unchecked = sum(not v.get() for v in self.checks[:2])
        self.summary.config(text=f"Band: {self.band.get()}\nLOF {lof} MHz · LNB preset {lnb}\n"
                                 f"SDR: {self.tuner.get()} → sweep {lo:g}-{hi:g} MHz with {tool}\n"
                                 + (f"Note: {warn}\n" if warn else "") +
                                 f"Power: {self.power.get()}"
                                 + ("\n\nWarning: the DC block and power-off checks are not ticked." if unchecked else ""))

    def finish(self):
        data = {"band": self.band.get(), "tuner": self.tuner.get(), "power": self.power.get()}
        save_settings(data)
        apply_settings(self.app, data)
        self.destroy()
        self.app.tabs.select(self.app.spectrum.frame)
        self.app.log("Setup wizard: settings applied.")


def apply_settings(app, data: dict) -> None:
    spec = app.spectrum
    band = data.get("band")
    if band not in BAND_PLANS:
        band = "Ku-band low (LO 9750)"
    tool = TUNERS.get(data.get("tuner"), TUNERS[next(iter(TUNERS))])[0]
    spec.tuner.set(data.get("tuner") if data.get("tuner") in TUNERS else next(iter(TUNERS)))
    spec.band.set(band)
    spec.source.set(tool)
    spec.apply_band()
    power = data.get("power", "")
    if "13 V" in power and "18" not in power:
        spec.pol.set("V")
    elif "18 V" in power and "13" not in power:
        spec.pol.set("H")
    if BAND_PLANS[band].lnb:
        app.tuning.v["lnb"].set(BAND_PLANS[band].lnb)
