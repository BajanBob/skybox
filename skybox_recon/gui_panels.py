"""Beryl desktop tabs: Spectrum & Finder, Blind Scan, Constellation,
Services/PIDs, Tuning, Dual Tuner, AV Stream and Advisor."""
from __future__ import annotations

import collections
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import dvb, spectrum
from .advisor import CognitiveAdvisor, acquisition_plan, identify_satellite, load_reference
from .gui_help import TUNERS

BG, PANEL, INK, SUB, ACCENT, AMBER, GREEN = "#0b1220", "#142238", "#e6edf7", "#9fb2cc", "#1677d2", "#f5c451", "#3ccf91"
PLOT_BG, GRID = "#07101d", "#1b2c44"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
SIM = "Simulated test signal"


def heading(parent, text, sub=None):
    ttk.Label(parent, text=text, style="Title.TLabel").pack(anchor="w")
    if sub:
        ttk.Label(parent, text=sub, style="Sub.TLabel", wraplength=1100, justify="left").pack(anchor="w", pady=(2, 8))


def field(parent, label, var, width=12, values=None, readonly=True):
    box = ttk.Frame(parent)
    box.pack(side="left", padx=(0, 12))
    ttk.Label(box, text=label, style="Sub.TLabel").pack(anchor="w")
    if values is not None:
        w = ttk.Combobox(box, textvariable=var, values=values, width=width,
                         state="readonly" if readonly else "normal")
    else:
        w = ttk.Entry(box, textvariable=var, width=width)
    w.pack(anchor="w")
    return w


def level_colour(q: float) -> str:
    q = max(0.0, min(1.0, q))
    stops = [(0.0, (8, 20, 60)), (0.35, (22, 90, 200)), (0.6, (60, 200, 245)), (0.8, (245, 224, 74)), (1.0, (239, 68, 68))]
    for (q0, c0), (q1, c1) in zip(stops, stops[1:]):
        if q <= q1:
            t = (q - q0) / (q1 - q0)
            return "#%02x%02x%02x" % tuple(int(a + (b - a) * t) for a, b in zip(c0, c1))
    return "#ef4444"


# --------------------------------------------------------------------------- #
# Spectrum & finder
# --------------------------------------------------------------------------- #

class SpectrumPanel:
    WF_W, WF_H = 640, 110

    def __init__(self, app, nb):
        self.app = app
        self.frame = ttk.Frame(nb, padding=14)
        nb.add(self.frame, text="Spectrum")
        heading(self.frame, "Spectrum analyser, waterfall and satellite finder",
                "Sweeps the 950-2150 MHz dish IF with an RTL-SDR (rtl_power) or HackRF One (hackrf_sweep). "
                "Power the LNB with 13/18 V from a receiver or power inserter. The finder beeps faster and higher "
                "as the signal rises and holds a steady tone at lock level.")
        row = ttk.Frame(self.frame)
        row.pack(fill="x", pady=(0, 8))
        self.source = tk.StringVar(value="rtl_power")
        field(row, "Source", self.source, 20, ["rtl_power", "hackrf_sweep", "CSV file…", SIM])
        self.lof = tk.StringVar(value="9750")
        field(row, "LNB LOF (MHz)", self.lof, 8, ["9750", "10600", "10000", "10700", "10750", "11250", "11300", "5150"], False)
        self.pol = tk.StringVar(value="H")
        field(row, "Polarization (LNB 18 V = H)", self.pol, 4, ["H", "V", "L", "R"])
        self.gain = tk.StringVar(value="30")
        field(row, "Gain (dB)", self.gain, 5)
        self.bin = tk.StringVar(value="1000")
        field(row, "Bin (kHz)", self.bin, 6, ["250", "500", "1000", "2000"])
        self.tuner = tk.StringVar(value=next(iter(TUNERS)))
        field(row, "Tuner", self.tuner, 24, list(TUNERS))
        btns = ttk.Frame(row)
        btns.pack(side="left", pady=(14, 0))
        self.start_btn = ttk.Button(btns, text="Start", style="Accent.TButton", command=self.start)
        self.start_btn.pack(side="left")
        ttk.Button(btns, text="Stop", command=self.stop).pack(side="left", padx=6)

        self.banner = tk.Label(self.frame, text="", bg=BG, fg=AMBER, font=("Segoe UI", 10, "bold"))
        self.banner.pack(anchor="w")
        body = ttk.Frame(self.frame)
        body.pack(fill="both", expand=True)
        left = ttk.Frame(body)
        left.pack(side="left", fill="both", expand=True)
        self.canvas = tk.Canvas(left, bg=PLOT_BG, height=250, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.wf_img = tk.PhotoImage(width=self.WF_W, height=self.WF_H)
        self.wf = tk.Canvas(left, bg=PLOT_BG, height=self.WF_H + 4, highlightthickness=0)
        self.wf.pack(fill="x", pady=(6, 0))
        self.wf_item = self.wf.create_image(0, 2, image=self.wf_img, anchor="nw")
        self.wf_rows: collections.deque = collections.deque(maxlen=self.WF_H)

        side = tk.Frame(body, bg=PANEL, padx=14, pady=12, width=250)
        side.pack(side="left", fill="y", padx=(12, 0))
        tk.Label(side, text="SAT FINDER", bg=PANEL, fg="#83a9d6", font=("Segoe UI", 9, "bold")).pack(anchor="w")
        self.cn_lbl = tk.Label(side, text="C/N  —", bg=PANEL, fg=INK, font=("Segoe UI", 22, "bold"))
        self.cn_lbl.pack(anchor="w", pady=(6, 0))
        self.meter = ttk.Progressbar(side, length=210, maximum=100)
        self.meter.pack(anchor="w", pady=6)
        self.peak_lbl = tk.Label(side, text="peak —", bg=PANEL, fg=SUB)
        self.peak_lbl.pack(anchor="w")
        self.lock_lbl = tk.Label(side, text="● NO LOCK", bg=PANEL, fg=AMBER, font=("Segoe UI", 11, "bold"))
        self.lock_lbl.pack(anchor="w", pady=(8, 8))
        self.beep = tk.BooleanVar(value=True)
        ttk.Checkbutton(side, text="Beep", variable=self.beep).pack(anchor="w")
        ttk.Button(side, text="Reset peak", command=lambda: self.finder.reset_peak()).pack(anchor="w", pady=6)
        wrow = tk.Frame(side, bg=PANEL)
        wrow.pack(anchor="w", pady=(8, 0))
        tk.Label(wrow, text="Watch window (IF MHz, blank = full band)", bg=PANEL, fg=SUB, wraplength=210,
                 justify="left").pack(anchor="w", pady=(0, 2))
        self.win_lo, self.win_hi = tk.StringVar(), tk.StringVar()
        ttk.Entry(wrow, textvariable=self.win_lo, width=7).pack(side="left")
        ttk.Entry(wrow, textvariable=self.win_hi, width=7).pack(side="left", padx=4)
        tk.Label(side, text="Simulated dish alignment", bg=PANEL, fg=SUB).pack(anchor="w", pady=(14, 0))
        self.sim_gain = tk.DoubleVar(value=0.6)
        ttk.Scale(side, from_=0.0, to=1.0, variable=self.sim_gain, length=210).pack(anchor="w")

        self.finder = spectrum.SatFinder()
        self.reading = None
        self.last = None            # (freqs, levels)
        self.live = None
        self._sim_job = None
        self._csv = []
        self._beeper = threading.Thread(target=self._beep_loop, daemon=True)
        self._beeper.start()
        self.canvas.bind("<Configure>", lambda e: self.draw())

    # ---- sources
    def start(self):
        self.stop()
        src = self.source.get()
        self.finder.window = self._window()
        if src == SIM:
            self.banner.config(text="SIMULATED TEST SIGNAL — not real reception. Move the alignment slider to hear the finder.")
            self._sim_tick()
            return
        if src == "CSV file…":
            path = filedialog.askopenfilename(title="rtl_power / hackrf_sweep CSV",
                                              filetypes=[("CSV", "*.csv"), ("All files", "*.*")])
            if not path:
                return
            with open(path, encoding="utf-8", errors="replace") as f:
                self._csv = spectrum.read_sweeps_csv(f.read())
            if not self._csv:
                messagebox.showerror("CSV", "No sweeps found in that file.")
                return
            self.banner.config(text=f"Replaying {os.path.basename(path)} ({len(self._csv)} sweeps)")
            self._csv_tick(0)
            return
        if not spectrum.tool_available(src):
            messagebox.showerror("SDR tool not found",
                                 f"{src} was not found on PATH.\n\nInstall the RTL-SDR or HackRF tools "
                                 "(rtl-sdr / hackrf packages; Windows: rtl-sdr-blog or PothosSDR release) "
                                 "and connect the SDR to the dish cable through an LNB power inserter.")
            return
        try:
            _t, lo, hi = TUNERS.get(self.tuner.get(), ("", 950.0, 2150.0))
            cmd = spectrum.sweep_command(src, lo, hi, bin_khz=int(self.bin.get()), gain=int(self.gain.get()))
        except ValueError as e:
            messagebox.showerror("Spectrum", str(e))
            return
        self.banner.config(text="LIVE: " + " ".join(cmd))
        self.app.log("Spectrum: " + " ".join(cmd))
        self.live = spectrum.LiveSweep(cmd, lambda f, l: self.app.call_ui(self.on_sweep, f, l),
                                       lambda m: self.app.call_ui(self.app.log, "Spectrum: " + m))
        self.live.start()

    def stop(self):
        if self.live:
            self.live.stop()
            self.live = None
        if self._sim_job:
            self.app.after_cancel(self._sim_job)
            self._sim_job = None
        self.banner.config(text="")

    def _sim_tick(self):
        from .testsignals import demo_sweep
        self.on_sweep(*demo_sweep(gain=self.sim_gain.get(), seed=int(time.time() * 10) % 1000))
        self._sim_job = self.app.after(700, self._sim_tick)

    def _csv_tick(self, i):
        self.on_sweep(*self._csv[i % len(self._csv)])
        self._sim_job = self.app.after(900, lambda: self._csv_tick(i + 1))

    def _window(self):
        try:
            lo, hi = float(self.win_lo.get()), float(self.win_hi.get())
            return (lo, hi) if hi > lo else None
        except ValueError:
            return None

    def lof_mhz(self) -> float:
        try:
            return float(self.lof.get())
        except ValueError:
            return 9750.0

    # ---- display
    def on_sweep(self, freqs, levels):
        self.last = (freqs, levels)
        self.finder.window = self._window()
        r = self.reading = self.finder.update(freqs, levels)
        self.cn_lbl.config(text=f"C/N {r.cn_db:4.1f} dB")
        self.meter["value"] = r.quality * 100
        self.peak_lbl.config(text=f"peak {r.peak_cn_db:.1f} dB   level {r.level_db:.1f} dB")
        self.lock_lbl.config(text="● SIGNAL LOCK LEVEL" if r.locked else "● NO LOCK", fg=GREEN if r.locked else AMBER)
        floor = spectrum.noise_floor(levels)
        top = max(levels)
        span = max(10.0, top - floor + 4)
        cols = []
        n = len(levels)
        for x in range(self.WF_W):
            v = levels[min(n - 1, x * n // self.WF_W)]
            cols.append(level_colour((v - floor + 2) / span))
        self.wf_rows.appendleft("{" + " ".join(cols) + "}")
        self.wf_img.put(" ".join(self.wf_rows), to=(0, 0))
        self.draw()

    def draw(self):
        c = self.canvas
        c.delete("all")
        w, h = max(200, c.winfo_width()), max(120, c.winfo_height())
        left, bottom = 46, h - 28
        if not self.last:
            c.create_text(w / 2, h / 2, text="Press Start to sweep", fill=SUB, font=("Segoe UI", 12))
            return
        freqs, levels = self.last
        lo_db = spectrum.noise_floor(levels) - 8
        hi_db = max(levels) + 4
        f0, f1 = freqs[0], freqs[-1]
        sx = lambda f: left + (f - f0) / max(1e-9, f1 - f0) * (w - left - 10)  # noqa: E731
        sy = lambda v: 10 + (hi_db - v) / max(1e-9, hi_db - lo_db) * (bottom - 10)  # noqa: E731
        for k in range(6):
            f = f0 + (f1 - f0) * k / 5
            x = sx(f)
            c.create_line(x, 10, x, bottom, fill=GRID)
            rf = dvb.if_to_rf(f, self.lof_mhz())
            c.create_text(x, bottom + 9, text=f"{f:.0f}", fill=SUB, font=("Consolas", 8))
            c.create_text(x, bottom + 20, text=f"{rf:.0f}", fill="#6f86a6", font=("Consolas", 8))
        for k in range(5):
            v = hi_db - (hi_db - lo_db) * k / 4
            y = sy(v)
            c.create_line(left, y, w - 10, y, fill=GRID)
            c.create_text(left - 6, y, text=f"{v:.0f}", fill=SUB, anchor="e", font=("Consolas", 8))
        c.create_text(4, bottom + 9, text="IF", fill=SUB, anchor="w", font=("Consolas", 8))
        c.create_text(4, bottom + 20, text="RF", fill="#6f86a6", anchor="w", font=("Consolas", 8))
        step = max(1, len(freqs) // 1500)
        pts = []
        for f, v in zip(freqs[::step], levels[::step]):
            pts += [sx(f), sy(v)]
        if len(pts) >= 4:
            c.create_line(*pts, fill=AMBER, width=1)
        win = self._window()
        if win:
            c.create_rectangle(sx(win[0]), 10, sx(win[1]), bottom, outline=ACCENT, dash=(3, 3))

    def _beep_loop(self):
        while True:
            r = self.reading
            if r and self.beep.get() and (self.live or self._sim_job):
                ms = 350 if r.locked else 90
                if not spectrum.play_tone(r.tone_hz, ms):
                    self.app.call_ui(self.app.bell)
                time.sleep(max(0.05, (r.interval_ms - ms) / 1000) if not r.locked else 0.05)
            else:
                time.sleep(0.2)


# --------------------------------------------------------------------------- #
# Blind scan
# --------------------------------------------------------------------------- #

class BlindScanPanel:
    def __init__(self, app, nb, spec: SpectrumPanel):
        self.app, self.spec = app, spec
        self.frame = ttk.Frame(nb, padding=14)
        nb.add(self.frame, text="Blind Scan")
        heading(self.frame, "Blind scan",
                "Finds every carrier in the latest sweep, estimates centre frequency and symbol rate from the "
                "-3 dB bandwidth (to within one sweep bin), filters duplicates and ranks by C/N. Scan each "
                "polarization (13 V / 18 V) and LNB band (22 kHz off / on) in turn.")
        row = ttk.Frame(self.frame)
        row.pack(fill="x", pady=(0, 8))
        self.threshold = tk.StringVar(value="3")
        field(row, "Threshold (dB over floor)", self.threshold, 6, ["2", "3", "4", "6", "8"])
        self.min_sr = tk.StringVar(value="100")
        field(row, "Min SR (ksym/s)", self.min_sr, 8)
        self.max_sr = tk.StringVar(value="72000")
        field(row, "Max SR (ksym/s)", self.max_sr, 8)
        b = ttk.Frame(row)
        b.pack(side="left", pady=(14, 0))
        ttk.Button(b, text="Scan latest sweep", style="Accent.TButton", command=self.scan).pack(side="left")
        ttk.Button(b, text="Send to Tuning", command=self.to_tuning).pack(side="left", padx=6)
        ttk.Button(b, text="Load transponder list…", command=self.load_ref).pack(side="left")
        cols = ("rf", "if", "pol", "sr", "bw", "cn")
        self.tree = ttk.Treeview(self.frame, columns=cols, show="headings", height=10)
        for c, t, wdt in zip(cols, ("RF MHz", "IF MHz", "Pol", "SR est. ksym/s", "-3 dB BW MHz", "C/N dB"),
                             (110, 90, 50, 130, 120, 80)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=wdt, anchor="e")
        self.tree.pack(fill="x")
        ttk.Label(self.frame, text="Advisor", style="Sub.TLabel").pack(anchor="w", pady=(10, 2))
        self.advice = tk.Text(self.frame, height=8, bg=PLOT_BG, fg=INK, wrap="word", relief="flat", font=("Consolas", 10))
        self.advice.pack(fill="both", expand=True)
        self.found = []
        self.reference = []
        self.advisor = CognitiveAdvisor()

    def scan(self):
        if not self.spec.last:
            messagebox.showinfo("Blind scan", "Start a sweep on the Spectrum tab first (or use the simulated test signal).")
            return
        try:
            th, lo, hi = float(self.threshold.get()), int(self.min_sr.get()), int(self.max_sr.get())
        except ValueError:
            messagebox.showerror("Blind scan", "Threshold and symbol rates must be numbers.")
            return
        freqs, levels = self.spec.last
        lof, pol = self.spec.lof_mhz(), self.spec.pol.get()
        self.found = spectrum.detect_transponders(freqs, levels, lof, pol, th, min_sr_ksym=lo, max_sr_ksym=hi)
        self.tree.delete(*self.tree.get_children())
        for t in sorted(self.found, key=lambda t: -t.snr_db):
            self.tree.insert("", "end", values=(f"{t.rf_mhz:.1f}", f"{t.if_mhz:.1f}", t.pol, t.sr_ksym,
                                                f"{t.bandwidth_mhz:.2f}", f"{t.snr_db:.1f}"))
        floor = spectrum.noise_floor(levels)
        self.advisor.record(self.found, lof, pol, floor)
        matches = identify_satellite(self.found, self.reference) if self.reference else None
        self.show_advice(self.advisor.advise(self.found, floor, lof, pol, reference_matches=matches))
        self.app.log(f"Blind scan: {len(self.found)} carriers ({pol}, LOF {lof:g})")
        return self.found

    def show_advice(self, tips):
        self.advice.delete("1.0", "end")
        self.advice.insert("end", "\n".join(str(t) for t in tips))

    def load_ref(self):
        path = filedialog.askopenfilename(title="Transponder list (CSV: satellite,orbital,freq_mhz,pol,sr_ksym)",
                                          filetypes=[("CSV", "*.csv"), ("All files", "*.*")])
        if path:
            self.reference = load_reference(path)
            self.app.log(f"Loaded {len(self.reference)} reference transponders from {os.path.basename(path)}")

    def to_tuning(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Blind scan", "Select a carrier first.")
            return
        rf, _if, pol, sr = self.tree.item(sel[0], "values")[:4]
        self.app.tuning.set_from(float(rf), int(sr) * 1000, pol)


# --------------------------------------------------------------------------- #
# Constellation
# --------------------------------------------------------------------------- #

class ConstellationPanel:
    def __init__(self, app, nb):
        self.app = app
        self.frame = ttk.Frame(nb, padding=14)
        nb.add(self.frame, text="Constellation")
        heading(self.frame, "Constellation and MER",
                "Demodulates a BPSK, QPSK or 8PSK carrier from an IQ capture: carrier offset, matched filter, "
                "symbol timing and phase recovery. The SDR's sample rate must exceed the symbol rate, so this "
                "suits narrow / low-symbol-rate carriers (RTL-SDR up to ~2.4 MS/s, HackRF up to 20 MS/s).")
        row = ttk.Frame(self.frame)
        row.pack(fill="x", pady=(0, 8))
        self.path = tk.StringVar()
        field(row, "IQ file (.cu8 rtl_sdr, .cs8 hackrf, .cf32)", self.path, 34)
        ttk.Button(row, text="Browse…", command=self.browse).pack(side="left", pady=(14, 0), padx=(0, 12))
        self.rate = tk.StringVar(value="2400000")
        field(row, "Sample rate (S/s)", self.rate, 10)
        self.sr = tk.StringVar(value="500000")
        field(row, "Symbol rate", self.sr, 10)
        self.mod = tk.StringVar(value="QPSK")
        field(row, "Modulation", self.mod, 6, ["BPSK", "QPSK", "8PSK"])
        self.rolloff = tk.StringVar(value="0.35")
        field(row, "Roll-off", self.rolloff, 5, ["0.35", "0.25", "0.20"])
        row2 = ttk.Frame(self.frame)
        row2.pack(fill="x", pady=(0, 8))
        ttk.Button(row2, text="Analyze file", style="Accent.TButton", command=self.analyze).pack(side="left")
        self.cap_tool = tk.StringVar(value="rtl_sdr")
        ttk.Combobox(row2, textvariable=self.cap_tool, values=["rtl_sdr", "hackrf_transfer"], width=14,
                     state="readonly").pack(side="left", padx=(16, 4))
        self.cap_freq = tk.StringVar(value="1200.0")
        ttk.Label(row2, text="IF MHz").pack(side="left")
        ttk.Entry(row2, textvariable=self.cap_freq, width=8).pack(side="left", padx=4)
        ttk.Button(row2, text="Capture 2 s and analyze", command=self.capture).pack(side="left", padx=4)
        ttk.Button(row2, text="Simulated QPSK", command=self.simulate).pack(side="left", padx=12)
        body = ttk.Frame(self.frame)
        body.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(body, width=380, height=380, bg=PLOT_BG, highlightthickness=0)
        self.canvas.pack(side="left")
        self.stats = tk.Label(body, text="No capture analysed yet.", bg=BG, fg=INK, justify="left",
                              font=("Consolas", 12), anchor="nw")
        self.stats.pack(side="left", fill="both", expand=True, padx=16)

    def browse(self):
        p = filedialog.askopenfilename(title="IQ capture", filetypes=[("IQ", "*.cu8 *.cs8 *.cf32 *.bin *.iq *.raw"),
                                                                     ("All files", "*.*")])
        if p:
            self.path.set(p)

    def _params(self):
        return float(self.rate.get()), float(self.sr.get()), {"BPSK": 2, "QPSK": 4, "8PSK": 8}[self.mod.get()], float(self.rolloff.get())

    def analyze(self, iq=None, label=None):
        try:
            from .constellation import load_iq, recover
        except ImportError:
            messagebox.showerror("Constellation", "numpy is required for the constellation (pip install numpy).")
            return
        try:
            rate, sr, order, ro = self._params()
            if iq is None:
                if not os.path.isfile(self.path.get()):
                    messagebox.showwarning("Constellation", "Choose an IQ file first.")
                    return
                iq = load_iq(self.path.get())
            r = recover(iq, rate, sr, order, ro)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Constellation", str(e))
            return
        self.plot(r.symbols)
        self.stats.config(text=(f"{label or os.path.basename(self.path.get())}\n\n"
                                f"{self.mod.get()}  {r.symbols.size} symbols\nMER    {r.mer_db:5.1f} dB\n"
                                f"EVM    {r.evm_pct:5.1f} %\noffset {r.freq_offset_hz:+.0f} Hz"))
        self.app.log(f"Constellation: MER {r.mer_db:.1f} dB, offset {r.freq_offset_hz:+.0f} Hz")

    def plot(self, syms):
        c = self.canvas
        c.delete("all")
        s, m = 380, 190
        c.create_line(m, 10, m, s - 10, fill=GRID)
        c.create_line(10, m, s - 10, m, fill=GRID)
        scale = 120
        for z in syms[:3000]:
            x, y = m + z.real * scale, m - z.imag * scale
            if 0 < x < s and 0 < y < s:
                c.create_rectangle(x, y, x + 1.6, y + 1.6, outline="", fill="#5ab0ff")

    def simulate(self):
        try:
            from .testsignals import demo_iq
        except ImportError:
            return
        self.rate.set("4000000")
        self.sr.set("1000000")
        self.mod.set("QPSK")
        self.analyze(demo_iq(order=4, snr_db=16, freq_offset=0.002), "SIMULATED QPSK (not real reception)")

    def capture(self):
        tool = self.cap_tool.get()
        if not shutil.which(tool):
            messagebox.showerror("Capture", f"{tool} was not found on PATH.")
            return
        try:
            centre = int(float(self.cap_freq.get()) * 1e6)
            rate = int(float(self.rate.get()))
        except ValueError:
            messagebox.showerror("Capture", "Frequency and sample rate must be numbers.")
            return
        from .constellation import capture_command
        out = os.path.join(tempfile.gettempdir(), "skybox-capture." + ("cu8" if tool == "rtl_sdr" else "cs8"))
        cmd = capture_command(tool, centre, rate, 2.0, out)
        self.app.log("Capture: " + " ".join(cmd))

        def work():
            try:
                subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, timeout=60, creationflags=NO_WINDOW)
                self.app.call_ui(self.path.set, out)
                self.app.call_ui(self.analyze)
            except Exception as e:  # noqa: BLE001
                self.app.call_ui(self.app.log, f"Capture failed: {e}")
        threading.Thread(target=work, daemon=True).start()


# --------------------------------------------------------------------------- #
# Services / PIDs
# --------------------------------------------------------------------------- #

class ServicesPanel:
    def __init__(self, app, nb):
        self.app = app
        self.frame = ttk.Frame(nb, padding=14)
        nb.add(self.frame, text="Services / PIDs")
        heading(self.frame, "Service, PID and satellite discovery",
                "Reads PAT, PMT, SDT and NIT from a transport stream: service names, video, audio, subtitle and "
                "PCR PIDs with codecs and languages, scrambling, and the orbital position announced by the network.")
        row = ttk.Frame(self.frame)
        row.pack(fill="x", pady=(0, 8))
        ttk.Button(row, text="Open .ts recording…", style="Accent.TButton", command=self.open).pack(side="left")
        ttk.Button(row, text="Simulated stream", command=self.simulate).pack(side="left", padx=8)
        self.summary = tk.Label(self.frame, text="", bg=BG, fg=AMBER, justify="left", font=("Segoe UI", 10, "bold"),
                                wraplength=1100, anchor="w")
        self.summary.pack(fill="x")
        cols = ("pid", "type", "codec", "lang")
        self.tree = ttk.Treeview(self.frame, columns=cols, height=14)
        self.tree.heading("#0", text="Service")
        self.tree.column("#0", width=300)
        for c, t, w in zip(cols, ("PID", "Type", "Codec", "Lang"), (120, 90, 280, 60)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w)
        self.tree.pack(fill="both", expand=True, pady=(6, 0))

    def open(self, path=None):
        path = path or filedialog.askopenfilename(title="Transport stream", filetypes=[("MPEG-TS", "*.ts *.mts *.m2ts *.trp"),
                                                                                    ("All files", "*.*")])
        if not path:
            return
        from .ts_parser import analyze_file
        self.show(analyze_file(path, max_bytes=128 << 20), os.path.basename(path))

    def simulate(self):
        from .testsignals import demo_transport_stream
        from .ts_parser import TSParser
        p = TSParser()
        p.feed(demo_transport_stream())
        self.show(p.report(), "SIMULATED stream (not real reception)")

    def show(self, rep, label):
        self.tree.delete(*self.tree.get_children())
        here = rep.this_transponder
        sat = ", ".join(rep.orbital_positions) or "not announced"
        txt = (f"{label}: {len(rep.services)} services, {rep.packets} packets, CC errors {rep.cc_errors}. "
               f"Network: {rep.network_name or '-'}. Satellite (from NIT): {sat}.")
        if here:
            txt += (f"  This transponder: {here.frequency_khz / 1000:.0f} MHz {here.polarization} "
                    f"{here.symbol_rate // 1000} ksym/s {here.modulation_system} {here.modulation} FEC {here.fec}.")
        self.summary.config(text=txt)
        for s in sorted(rep.services, key=lambda s: s.service_id):
            name = f"{s.service_id}  {s.service_name or '(no name)'}" + ("  [scrambled]" if s.scrambled else "")
            node = self.tree.insert("", "end", text=name, open=True,
                                    values=(f"PMT 0x{s.pmt_pid:04x}", rep.service_types.get(s.service_id, ""), "", ""))
            self.tree.insert(node, "end", text="PCR", values=(f"0x{s.pcr_pid:04x} ({s.pcr_pid})", "PCR", "", ""))
            for comp in s.components:
                self.tree.insert(node, "end", text=comp.component_type,
                                 values=(f"0x{comp.pid:04x} ({comp.pid})", comp.component_type, comp.codec or "",
                                         comp.language or ""))
        self.app.log(f"Services/PIDs: {label}: {len(rep.services)} services; satellite {sat}")
        self.app.last_report = rep


# --------------------------------------------------------------------------- #
# Tuning
# --------------------------------------------------------------------------- #

class TuningPanel:
    def __init__(self, app, nb):
        self.app = app
        self.frame = ttk.Frame(nb, padding=14)
        nb.add(self.frame, text="Tuning")
        heading(self.frame, "DVB-S / S2 / S2X tuning",
                "Builds a dvbv5 channel file and dvbv5-zap command (Linux DVB frontends). LNB band and 22 kHz "
                "tone follow from the RF frequency; 13 V selects V/R, 18 V selects H/L.")
        g = ttk.Frame(self.frame)
        g.pack(fill="x")
        self.v = {k: tk.StringVar(value=d) for k, d in (
            ("freq", "11778.0"), ("sr", "27500000"), ("delsys", "DVBS2"), ("mod", "auto"), ("fec", "auto"),
            ("pol", "V"), ("rolloff", "auto"), ("pilot", "auto"), ("inversion", "auto"), ("mis", ""),
            ("pls", ""), ("pls_mode", "ROOT"), ("diseqc", "none"), ("lnb", "UNIVERSAL"), ("service", "ch1"))}
        rows = [[("RF frequency (MHz)", "freq", None), ("Symbol rate (sym/s)", "sr", None),
                 ("Standard", "delsys", list(dvb.MODULATIONS)), ("Modulation", "mod", list(dvb.ALL_MODULATIONS)),
                 ("FEC", "fec", list(dvb.FEC))],
                [("Polarization", "pol", ["H", "V", "L", "R"]), ("Roll-off", "rolloff", list(dvb.ROLLOFF)),
                 ("Pilot", "pilot", list(dvb.PILOT)), ("Spectral inversion", "inversion", list(dvb.INVERSION)),
                 ("LNB", "lnb", list(dvb.LNBS))],
                [("Stream ID / MIS", "mis", None), ("PLS code", "pls", None), ("PLS mode", "pls_mode", list(dvb.PLS_MODES)),
                 ("DiSEqC port", "diseqc", ["none", "0", "1", "2", "3"]), ("Service name", "service", None)]]
        for r in rows:
            fr = ttk.Frame(g)
            fr.pack(fill="x", pady=4)
            for label, key, values in r:
                field(fr, label, self.v[key], 16, values)
        b = ttk.Frame(self.frame)
        b.pack(fill="x", pady=8)
        ttk.Button(b, text="Build channel file and command", style="Accent.TButton", command=self.build).pack(side="left")
        self.lnb_info = ttk.Label(b, text="", style="Sub.TLabel")
        self.lnb_info.pack(side="left", padx=12)
        self.out = tk.Text(self.frame, height=14, bg=PLOT_BG, fg=INK, relief="flat", font=("Consolas", 10))
        self.out.pack(fill="both", expand=True)

    def params(self) -> dvb.TuneParams:
        v = {k: x.get().strip() for k, x in self.v.items()}
        p = dvb.TuneParams(freq_khz=int(round(float(v["freq"]) * 1000)), sr=int(v["sr"]), delsys=v["delsys"],
                           mod=v["mod"], fec=v["fec"], pol=v["pol"], rolloff=v["rolloff"], pilot=v["pilot"],
                           inversion=v["inversion"], isi=int(v["mis"]) if v["mis"] else None,
                           pls_code=int(v["pls"]) if v["pls"] else None, pls_mode=v["pls_mode"],
                           sat_number=None if v["diseqc"] == "none" else int(v["diseqc"]), service=v["service"] or "ch1")
        p.validate()
        return p

    def build(self):
        try:
            p = self.params()
            conf = dvb.dvbv5_conf(p)
        except ValueError as e:
            messagebox.showerror("Tuning", str(e))
            return
        lnb = self.v["lnb"].get()
        lof, tone = dvb.lnb_for(p.freq_khz / 1000, lnb)
        if_mhz = dvb.rf_to_if(p.freq_khz / 1000, lof)
        self.lnb_info.config(text=f"LOF {lof:g} MHz · IF {if_mhz:.1f} MHz · 22 kHz {'on' if tone else 'off'} · "
                                  f"{dvb.voltage_for(p.pol)} V")
        path = os.path.join(tempfile.gettempdir(), f"{p.service}.conf")
        cmd = dvb.dvbv5_zap_cmd(path, p, lnb=lnb, out="capture.ts")
        self.out.delete("1.0", "end")
        self.out.insert("end", f"# {path}\n{conf}\n# command (Linux, DVB-S2 adapter)\n{subprocess.list2cmdline(cmd)}\n")
        if not (dvb.IF_MIN_MHZ <= if_mhz <= dvb.IF_MAX_MHZ):
            self.out.insert("end", f"\nWARNING: IF {if_mhz:.0f} MHz is outside 950-2150 MHz for this LNB.\n")

    def set_from(self, rf_mhz: float, sr: int, pol: str):
        self.v["freq"].set(f"{rf_mhz:.1f}")
        self.v["sr"].set(str(sr))
        if pol in ("H", "V", "L", "R"):
            self.v["pol"].set(pol)
        self.app.tabs.select(self.frame)
        self.build()


# --------------------------------------------------------------------------- #
# Dual tuner
# --------------------------------------------------------------------------- #

class DualTunerPanel:
    def __init__(self, app, nb):
        self.app = app
        self.frame = ttk.Frame(nb, padding=14)
        nb.add(self.frame, text="Dual Tuner")
        heading(self.frame, "Dual tuner A / B",
                "Drives two Linux DVB adapters independently: for example Tuner A on live view or recording while "
                "Tuner B scans or monitors another transponder or satellite. Needs two adapters with separate RF "
                "inputs (two LNB cables or a dual-output LNB); one tuner cannot be split in software.")
        self.adapters = dvb.list_dvb_adapters()
        self.status = ttk.Label(self.frame, style="Sub.TLabel",
                                text=f"DVB adapters found: {self.adapters}" if self.adapters else
                                "No DVB adapters found (Linux /dev/dvb). Controls stay disabled on this computer.")
        self.status.pack(anchor="w")
        self.separate = tk.BooleanVar(value=False)
        ttk.Checkbutton(self.frame, text="I confirm the two adapters have separate RF inputs",
                        variable=self.separate).pack(anchor="w", pady=6)
        cols = ttk.Frame(self.frame)
        cols.pack(fill="x")
        self.ctrl = None
        self.vars = {}
        for t, task in (("A", "Live view / recording"), ("B", "Scan / monitoring")):
            box = tk.Frame(cols, bg=PANEL, padx=12, pady=10)
            box.pack(side="left", fill="both", expand=True, padx=(0, 10))
            tk.Label(box, text=f"TUNER {t}", bg=PANEL, fg="#83a9d6", font=("Segoe UI", 10, "bold")).pack(anchor="w")
            v = {k: tk.StringVar(value=d) for k, d in (("adapter", str(self.adapters[0 if t == "A" else -1]) if self.adapters else "0"),
                                                       ("freq", "11778.0" if t == "A" else "10847.0"),
                                                       ("sr", "27500000" if t == "A" else "23000000"),
                                                       ("pol", "V" if t == "A" else "H"),
                                                       ("delsys", "DVBS2" if t == "A" else "DVBS"),
                                                       ("task", task), ("lnb", "UNIVERSAL"))}
            self.vars[t] = v
            r1 = tk.Frame(box, bg=PANEL)
            r1.pack(fill="x", pady=4)
            for label, key, values in (("Adapter", "adapter", [str(a) for a in self.adapters] or ["0", "1"]),
                                       ("RF MHz", "freq", None), ("SR", "sr", None)):
                field(r1, label, v[key], 10, values)
            r2 = tk.Frame(box, bg=PANEL)
            r2.pack(fill="x", pady=4)
            for label, key, values in (("Pol", "pol", ["H", "V", "L", "R"]), ("Standard", "delsys", list(dvb.MODULATIONS)),
                                       ("LNB", "lnb", list(dvb.LNBS)), ("Task", "task", None)):
                field(r2, label, v[key], 12 if key == "task" else 8, values)
            r3 = tk.Frame(box, bg=PANEL)
            r3.pack(fill="x", pady=(6, 0))
            ttk.Button(r3, text="Tune", style="Accent.TButton", command=lambda t=t: self.tune(t)).pack(side="left")
            ttk.Button(r3, text="Stop", command=lambda t=t: self.stop(t)).pack(side="left", padx=6)
            lbl = tk.Label(r3, text="idle", bg=PANEL, fg=SUB)
            lbl.pack(side="left", padx=8)
            v["_lbl"] = lbl
            if not self.adapters:
                for w in r3.winfo_children():
                    if isinstance(w, ttk.Button):
                        w.state(["disabled"])
        self.app.after(2000, self.poll)

    def tune(self, t):
        from .dualtuner import DualTunerController
        try:
            if self.ctrl is None:
                a, b = int(self.vars["A"]["adapter"].get()), int(self.vars["B"]["adapter"].get())
                self.ctrl = DualTunerController(a, b, self.separate.get())
            v = self.vars[t]
            p = dvb.TuneParams(freq_khz=int(float(v["freq"].get()) * 1000), sr=int(v["sr"].get()),
                               delsys=v["delsys"].get(), pol=v["pol"].get(), service=f"tuner{t}")
            cmd = self.ctrl.tune(t, p, v["task"].get(), lnb=v["lnb"].get())
            self.app.log(f"Tuner {t}: " + " ".join(cmd))
        except (ValueError, OSError) as e:
            messagebox.showerror(f"Tuner {t}", str(e))

    def stop(self, t):
        if self.ctrl:
            self.ctrl.stop(t)

    def poll(self):
        if self.ctrl:
            for t, s in self.ctrl.poll().items():
                self.vars[t]["_lbl"].config(text=f"{s['state']}{' · LOCK' if s['locked'] else ''} · {s['task'] or ''}",
                                            fg=GREEN if s["locked"] else SUB)
        self.app.after(2000, self.poll)


# --------------------------------------------------------------------------- #
# AV stream
# --------------------------------------------------------------------------- #

class StreamPanel:
    def __init__(self, app, nb):
        self.app = app
        self.frame = ttk.Frame(nb, padding=14)
        nb.add(self.frame, text="AV Stream")
        heading(self.frame, "Wireless audio / video streaming",
                "Serves a transport stream to players on your local network (Wi-Fi 6 or any LAN): VLC, Kodi, mpv, "
                "smart TVs and phones. No internet connection is used. Follow mode streams a recording while a "
                "tuner is still writing it.")
        row = ttk.Frame(self.frame)
        row.pack(fill="x", pady=(0, 8))
        self.src = tk.StringVar()
        field(row, "Source .ts", self.src, 40)
        ttk.Button(row, text="Browse…", command=self.browse).pack(side="left", pady=(14, 0), padx=(0, 12))
        self.port = tk.StringVar(value="8090")
        field(row, "Port", self.port, 6)
        self.follow = tk.BooleanVar(value=False)
        ttk.Checkbutton(row, text="Follow live recording", variable=self.follow).pack(side="left", pady=(14, 0))
        b = ttk.Frame(self.frame)
        b.pack(fill="x")
        ttk.Button(b, text="Start streaming", style="Accent.TButton", command=self.start).pack(side="left")
        ttk.Button(b, text="Stop", command=self.stop).pack(side="left", padx=6)
        self.info = tk.Label(self.frame, text="Not streaming.", bg=BG, fg=INK, justify="left", font=("Consolas", 12),
                             anchor="w")
        self.info.pack(fill="x", pady=12)
        self.server = None
        self.app.after(1000, self.tick)

    def browse(self):
        p = filedialog.askopenfilename(title="Transport stream", filetypes=[("MPEG-TS", "*.ts *.mts *.trp"), ("All files", "*.*")])
        if p:
            self.src.set(p)

    def start(self):
        from .streamer import TSStreamServer
        self.stop()
        try:
            self.server = TSStreamServer(self.src.get(), port=int(self.port.get()), follow=self.follow.get(),
                                         loop=not self.follow.get())
            self.server.start()
        except (OSError, ValueError) as e:
            self.server = None
            messagebox.showerror("AV stream", f"Could not start: {e}")
            return
        self.app.log("AV stream: " + ", ".join(self.server.urls()))

    def stop(self):
        if self.server:
            self.server.stop()
            self.server = None

    def tick(self):
        if self.server:
            self.info.config(text="Open one of these in VLC / Kodi / mpv on the same network:\n  "
                             + "\n  ".join(self.server.urls())
                             + f"\n\nclients {self.server.clients}   sent {self.server.bytes_sent / 1e6:.1f} MB")
        else:
            self.info.config(text="Not streaming.")
        self.app.after(1000, self.tick)


# --------------------------------------------------------------------------- #
# Advisor / auto-acquire
# --------------------------------------------------------------------------- #

class AdvisorPanel:
    def __init__(self, app, nb, spec: SpectrumPanel, scan: BlindScanPanel, services: ServicesPanel, tuning: TuningPanel):
        self.app, self.spec, self.scan, self.services, self.tuning = app, spec, scan, services, tuning
        self.frame = ttk.Frame(nb, padding=14)
        nb.add(self.frame, text="Advisor")
        heading(self.frame, "Cognitive receiver",
                "Runs the acquisition sequence automatically and learns from scan history: sweep, detect carriers, "
                "rank and advise, tune the strongest, record, then identify services, PIDs and the satellite from "
                "the NIT. Steps that need hardware you don't have are skipped and explained. Everything runs locally.")
        b = ttk.Frame(self.frame)
        b.pack(fill="x", pady=(0, 8))
        ttk.Button(b, text="Auto-acquire", style="Accent.TButton", command=self.run).pack(side="left")
        self.plan_box = tk.Text(self.frame, height=8, bg=PLOT_BG, fg=INK, relief="flat", font=("Consolas", 11))
        self.plan_box.pack(fill="x")
        ttk.Label(self.frame, text="Advice", style="Sub.TLabel").pack(anchor="w", pady=(10, 2))
        self.advice = tk.Text(self.frame, height=10, bg=PLOT_BG, fg=INK, wrap="word", relief="flat", font=("Consolas", 10))
        self.advice.pack(fill="both", expand=True)

    def show_plan(self, plan):
        marks = {"pending": "·", "running": "→", "done": "✓", "skipped": "–", "failed": "✗"}
        self.plan_box.delete("1.0", "end")
        for s in plan:
            self.plan_box.insert("end", f" {marks[s.status]} {s.name:<48} {s.status:<8} {s.detail}\n")

    def run(self):
        simulated = self.spec.source.get() == SIM
        have_sdr = simulated or bool(self.spec.last) or spectrum.tool_available(self.spec.source.get())
        have_dvb = bool(dvb.list_dvb_adapters()) and shutil.which("dvbv5-zap") is not None
        plan = acquisition_plan(have_sdr, have_dvb or simulated)
        self.show_plan(plan)
        threading.Thread(target=self._work, args=(plan, simulated), daemon=True).start()

    def _step(self, plan, i, status, detail=""):
        plan[i].status, plan[i].detail = status, detail
        self.app.call_ui(self.show_plan, plan)

    def _work(self, plan, simulated):
        found, rep = [], None
        try:
            if plan[0].status != "skipped":
                self._step(plan, 0, "running")
                if simulated:
                    from .testsignals import demo_sweep
                    sweep = demo_sweep(seed=9)
                    self.app.call_ui(self.spec.on_sweep, *sweep)
                elif self.spec.last:
                    sweep = self.spec.last
                else:
                    _t, lo, hi = TUNERS.get(self.spec.tuner.get(), ("", 950.0, 2150.0))
                    cmd = spectrum.sweep_command(self.spec.source.get(), lo, hi, once=True)
                    out = subprocess.run(cmd, capture_output=True, text=True, timeout=300, creationflags=NO_WINDOW)
                    sweeps = spectrum.read_sweeps_csv(out.stdout)
                    if not sweeps:
                        raise RuntimeError(f"{cmd[0]} returned no data")
                    sweep = sweeps[-1]
                    self.app.call_ui(self.spec.on_sweep, *sweep)
                self._step(plan, 0, "done", "SIMULATED" if simulated else "")
                self._step(plan, 1, "running")
                time.sleep(0.3)
                done = threading.Event()
                box = {}

                def scan_ui():
                    box["found"] = self.scan.scan() or []
                    done.set()
                self.app.call_ui(scan_ui)
                done.wait(10)
                found = box.get("found", [])
                self._step(plan, 1, "done", f"{len(found)} carriers")
                self._step(plan, 2, "done", "see Advice")
            if plan[3].status != "skipped" and found:
                best = max(found, key=lambda t: t.snr_db)
                self._step(plan, 3, "running", f"{best.rf_mhz:.0f} MHz {best.pol}")
                if simulated:
                    from .testsignals import demo_transport_stream
                    from .ts_parser import TSParser
                    time.sleep(0.5)
                    self._step(plan, 3, "done", "SIMULATED")
                    self._step(plan, 4, "done", "SIMULATED")
                    p = TSParser()
                    p.feed(demo_transport_stream())
                    rep = p.report()
                    self.app.call_ui(self.services.show, rep, "SIMULATED stream (not real reception)")
                else:
                    params = dvb.TuneParams(freq_khz=int(best.rf_mhz * 1000), sr=best.sr_ksym * 1000,
                                            pol=best.pol if best.pol in "HVLR" else "H", service="auto")
                    conf = os.path.join(tempfile.gettempdir(), "skybox-auto.conf")
                    with open(conf, "w", encoding="utf-8") as f:
                        f.write(dvb.dvbv5_conf(params))
                    out_ts = os.path.join(tempfile.gettempdir(), "skybox-auto.ts")
                    cmd = dvb.dvbv5_zap_cmd(conf, params, out=out_ts, seconds=10)
                    cmd.insert(1, "-P")
                    self._step(plan, 4, "running", "10 s")
                    subprocess.run(cmd, capture_output=True, timeout=40)
                    if not os.path.exists(out_ts) or os.path.getsize(out_ts) == 0:
                        self._step(plan, 3, "failed", "no lock (check SR / polarization / LNB)")
                        self._step(plan, 4, "failed")
                    else:
                        self._step(plan, 3, "done")
                        self._step(plan, 4, "done", f"{os.path.getsize(out_ts) // 1024} KiB")
                        from .ts_parser import analyze_file
                        rep = analyze_file(out_ts)
                        self.app.call_ui(self.services.show, rep, "auto-acquire recording")
                if rep is not None:
                    self._step(plan, 5, "done", ", ".join(rep.orbital_positions) or "no NIT position")
            if self.spec.last:
                floor = spectrum.noise_floor(self.spec.last[1])
                tips = self.scan.advisor.advise(found, floor, self.spec.lof_mhz(), self.spec.pol.get(),
                                                nit_positions=rep.orbital_positions if rep else None)
                self.app.call_ui(self._show_advice, tips)
        except Exception as e:  # noqa: BLE001
            self.app.call_ui(self.app.log, f"Auto-acquire stopped: {e}")
            for s in plan:
                if s.status == "running":
                    s.status, s.detail = "failed", str(e)[:60]
            self.app.call_ui(self.show_plan, plan)

    def _show_advice(self, tips):
        self.advice.delete("1.0", "end")
        self.advice.insert("end", "\n".join(str(t) for t in tips))
