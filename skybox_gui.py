"""Skybox Recon V2 -- Windows/desktop GUI around the skybox.py command engine.

One executable does both jobs:
  SkyboxRecon.exe                 -> opens the persistent desktop window
  SkyboxRecon.exe --cli <args>    -> runs the skybox.py engine (used internally
                                     by the GUI so no second .exe is required)
  SkyboxRecon.exe --smoke-test    -> builds the window, closes it after a
                                     moment and exits 0 (used by CI)
"""
from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import traceback

APP_TITLE = "SKYBOX RECON — Control Centre"
FROZEN = bool(getattr(sys, "frozen", False))

# Folder the user actually sees. In a PyInstaller one-file build __file__ lives
# in a temporary _MEI extraction folder that is deleted on exit, so it must not
# be used for user-facing paths (that was the cause of the missing-engine bug).
APP_DIR = (os.path.dirname(os.path.abspath(sys.executable)) if FROZEN
           else os.path.dirname(os.path.abspath(__file__)))
CLI_SCRIPT = os.path.join(APP_DIR, "skybox.py")
CRASH_LOG = os.path.join(APP_DIR, "SkyboxRecon-error.log")
# Read-only files bundled into the executable (icon); _MEIPASS when frozen.
BUNDLE_DIR = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))

try:
    from skybox import CODENAME, VERSION as APP_VERSION
except Exception:  # noqa: BLE001
    APP_VERSION, CODENAME = "6.0.0", "Beryl"

DONE = object()  # worker-finished marker passed through the event queue

# Hide the console window that would otherwise flash up for every engine call.
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0


def cli_command(args: list[str]) -> list[str]:
    """Command line that runs the skybox.py engine for source and frozen builds."""
    if FROZEN:
        return [sys.executable, "--cli", *args]
    return [sys.executable, CLI_SCRIPT, *args]


def run_engine_inline(argv: list[str]) -> int:
    """`--cli` mode: run skybox.py inside this process (frozen build)."""
    # A windowed exe has no console; keep print() from failing if the parent
    # did not give us pipes.
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    import skybox  # bundled by PyInstaller because of this import
    return int(skybox.main(argv) or 0)


def write_crash_log(text: str) -> str:
    for path in (CRASH_LOG, os.path.join(os.path.expanduser("~"), "SkyboxRecon-error.log")):
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(text + "\n")
            return path
        except OSError:
            continue
    return ""


import tkinter as tk  # noqa: E402
from tkinter import ttk, filedialog, messagebox  # noqa: E402


class SkyboxGUI(tk.Tk):
    def __init__(self, smoke: bool = False) -> None:
        super().__init__()
        self._events: queue.Queue = queue.Queue()
        self._calls: queue.Queue = queue.Queue()
        self.last_report = None
        self.title(f"{APP_TITLE}  v{APP_VERSION} {CODENAME}")
        try:
            self._icon = tk.PhotoImage(file=os.path.join(BUNDLE_DIR, "assets", "icon.png"))
            self.iconphoto(True, self._icon)
        except tk.TclError:
            pass
        self.geometry("1320x860")
        self.minsize(1100, 720)
        self.configure(bg="#0b1220")
        self.report_callback_exception = self._callback_error
        self._style()
        self._build()
        self.log("GUI started. Receiver is offline until connected.")
        self.log(f"Application folder: {APP_DIR}")
        self.log("Open Diagnostics / Log → Run self-test to check the command engine.")
        self.after(100, self._drain_events)
        from skybox_recon import gui_help
        self.after(300, lambda: self.log(f"Hover help: {gui_help.attach_tips(self)} tips ready."))
        settings = gui_help.load_settings()
        if settings:
            gui_help.apply_settings(self, settings)
        elif not smoke:
            self.after(800, self.open_wizard)

    # ------------------------------------------------------------------ style
    def _style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(".", font=("Segoe UI", 10))
        style.configure("TFrame", background="#101a2b")
        style.configure("Panel.TFrame", background="#142238")
        style.configure("TLabel", background="#101a2b", foreground="#e6edf7")
        style.configure("TCheckbutton", background="#101a2b", foreground="#e6edf7")
        style.configure("TRadiobutton", background="#101a2b", foreground="#e6edf7")
        style.map("TRadiobutton", background=[("active", "#142238")])
        style.map("TCheckbutton", background=[("active", "#142238")])
        style.configure("Treeview", background="#0d1828", fieldbackground="#0d1828", foreground="#e6edf7",
                        rowheight=24)
        style.configure("Treeview.Heading", background="#1a2b43", foreground="#dce8f8")
        style.configure("Title.TLabel", font=("Segoe UI", 21, "bold"), foreground="#f4f8ff")
        style.configure("Sub.TLabel", foreground="#9fb2cc")
        style.configure("Status.TLabel", foreground="#f5c451")
        style.configure("TButton", padding=8)
        style.configure("Accent.TButton", background="#1677d2", foreground="white")
        style.map("Accent.TButton", background=[("active", "#2b8be6")])
        style.configure("TNotebook", background="#0b1220", borderwidth=0)
        style.configure("TNotebook.Tab", padding=(10, 7), background="#1a2b43", foreground="#dce8f8")
        style.map("TNotebook.Tab", background=[("selected", "#1677d2")],
                  foreground=[("selected", "white")])

    # ------------------------------------------------------------------ layout
    def _build(self) -> None:
        header = ttk.Frame(self, padding=(20, 16))
        header.pack(fill="x")
        ttk.Label(header, text="◉  SKYBOX RECON", style="Title.TLabel").pack(side="left")
        ttk.Label(header, text="ALi M3510 / M3510A RECEIVER TOOLKIT",
                  style="Sub.TLabel").pack(side="left", padx=18, pady=(8, 0))
        self.status = tk.StringVar(value="●  OFFLINE — receiver not connected")
        ttk.Label(header, textvariable=self.status, style="Status.TLabel").pack(side="right", pady=8)

        summary = ttk.Frame(self, padding=(20, 0, 20, 14))
        summary.pack(fill="x")
        for title, value in [
            ("RECEIVER", "Not connected"),
            ("CONTROL MODE", "Local / offline"),
            ("HARDWARE WRITE", "Not exposed in GUI"),
            ("RELEASE", f"{CODENAME}"),
            ("APPLICATION", f"Desktop v{APP_VERSION}"),
        ]:
            card = ttk.Frame(summary, style="Panel.TFrame", padding=12)
            card.pack(side="left", fill="x", expand=True, padx=(0, 10))
            tk.Label(card, text=title, bg="#142238", fg="#83a9d6",
                     font=("Segoe UI", 8, "bold")).pack(anchor="w")
            tk.Label(card, text=value, bg="#142238", fg="#f4f8ff",
                     font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(4, 0))

        # Footer is packed before the notebook so it is never squeezed off-screen.
        footer = ttk.Frame(self, padding=(20, 4, 20, 12))
        footer.pack(side="bottom", fill="x")
        ttk.Label(
            footer,
            text=f"Skybox Recon v{APP_VERSION} • Hardware functions require compatible receiver interfaces/drivers",
            style="Sub.TLabel",
        ).pack(side="left")
        ttk.Button(footer, text="Open application folder",
                   command=lambda: self.open_path(APP_DIR)).pack(side="right")
        ttk.Button(footer, text="Setup wizard", style="Accent.TButton",
                   command=self.open_wizard).pack(side="right", padx=8)

        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill="both", expand=True, padx=20, pady=(0, 12))
        self.dashboard = ttk.Frame(self.tabs, padding=18)
        from skybox_recon import gui_panels as gp
        self.spectrum = gp.SpectrumPanel(self, self.tabs)
        self.blindscan = gp.BlindScanPanel(self, self.tabs, self.spectrum)
        self.constellation = gp.ConstellationPanel(self, self.tabs)
        self.services = gp.ServicesPanel(self, self.tabs)
        self.tuning = gp.TuningPanel(self, self.tabs)
        self.tune_tab = self.tuning.frame
        self.dual = gp.DualTunerPanel(self, self.tabs)
        self.stream = gp.StreamPanel(self, self.tabs)
        self.advisor = gp.AdvisorPanel(self, self.tabs, self.spectrum, self.blindscan, self.services, self.tuning)
        self.fw_tab = self._firmware_tab()
        self.serial_tab = self._serial_tab()
        self.diag_tab = self._diagnostics_tab()
        self._overview()
        self.spectrum.apply_band()

    def _overview(self) -> None:
        self.tabs.insert(0, self.dashboard, text="Overview")
        self.tabs.select(self.dashboard)
        ttk.Label(self.dashboard, text="Receiver control centre",
                  style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            self.dashboard,
            text="Launch diagnostics and supported analysis tools from one persistent window.",
            style="Sub.TLabel",
        ).pack(anchor="w", pady=(4, 18))
        grid = ttk.Frame(self.dashboard)
        grid.pack(fill="x")
        go = self.tabs.select
        items = [
            ("Spectrum & finder", "Live L-band spectrum, waterfall and finder beep (RTL-SDR / HackRF).",
             lambda: go(self.spectrum.frame)),
            ("Blind scan", "Detect transponders and estimate symbol rates.", lambda: go(self.blindscan.frame)),
            ("Services / PIDs", "Services, PIDs, codecs and satellite position from a TS.",
             lambda: go(self.services.frame)),
            ("Constellation", "Constellation and MER from an IQ capture.", lambda: go(self.constellation.frame)),
            ("Auto-acquire", "Sweep, detect, tune, identify: the cognitive receiver.", lambda: go(self.advisor.frame)),
            ("Dual tuner", "Two DVB adapters, independent tasks.", lambda: go(self.dual.frame)),
            ("AV stream", "Stream to players on the local network.", lambda: go(self.stream.frame)),
            ("Diagnostics", "Run the offline self-test suite.", lambda: self.run_cli(["selftest"], "Self-test")),
        ]
        for i, (title, desc, action) in enumerate(items):
            panel = ttk.Frame(grid, style="Panel.TFrame", padding=16)
            panel.grid(row=i // 4, column=i % 4, sticky="nsew", padx=6, pady=6)
            grid.columnconfigure(i % 4, weight=1)
            tk.Label(panel, text=title, bg="#142238", fg="#f4f8ff",
                     font=("Segoe UI", 14, "bold")).pack(anchor="w")
            tk.Label(panel, text=desc, bg="#142238", fg="#9fb2cc",
                     wraplength=250, justify="left").pack(anchor="w", pady=8)
            ttk.Button(panel, text="Open", command=action,
                       style="Accent.TButton").pack(anchor="w")
        tk.Label(
            self.dashboard,
            text=("HARDWARE: live spectrum, finder and constellation need an RTL-SDR or HackRF on the dish "
                  "cable with LNB power (13/18 V inserter). Tuning, auto-acquire recording and the dual tuner need "
                  "Linux DVB-S2 adapters with dvbv5-zap. Services/PIDs, streaming, firmware and self-test work on "
                  "any computer. Every simulated source is labelled."),
            bg="#3a2b16", fg="#ffd78a", wraplength=1000,
            justify="left", padx=12, pady=12,
        ).pack(fill="x", pady=(18, 0))

    def _firmware_tab(self) -> ttk.Frame:
        tab = ttk.Frame(self.tabs, padding=18)
        self.tabs.add(tab, text="Firmware Lab")
        ttk.Label(tab, text="Firmware image analysis", style="Title.TLabel").pack(anchor="w")
        row = ttk.Frame(tab)
        row.pack(fill="x", pady=12)
        self.fw_path = tk.StringVar()
        ttk.Entry(row, textvariable=self.fw_path).pack(side="left", fill="x",
                                                      expand=True, padx=(0, 8))
        ttk.Button(row, text="Browse…", command=self.choose_firmware).pack(side="left")
        ttk.Button(tab, text="Analyze image", command=self.analyze_firmware,
                   style="Accent.TButton").pack(anchor="w")
        ttk.Label(tab, text="Read-only analysis. Firmware flashing is not exposed.",
                  style="Sub.TLabel").pack(anchor="w", pady=10)
        return tab

    def _serial_tab(self) -> ttk.Frame:
        tab = ttk.Frame(self.tabs, padding=18)
        self.tabs.add(tab, text="Serial / UART")
        ttk.Label(tab, text="Serial console discovery", style="Title.TLabel").pack(anchor="w")
        row = ttk.Frame(tab)
        row.pack(anchor="w", pady=14)
        ttk.Label(row, text="Port").pack(side="left", padx=(0, 8))
        self.port = tk.StringVar(value="COM3" if sys.platform == "win32" else "/dev/ttyUSB0")
        self.port_box = ttk.Combobox(row, textvariable=self.port, width=18)
        self.port_box.pack(side="left", padx=(0, 6))
        ttk.Button(row, text="Refresh", command=self.refresh_ports).pack(side="left", padx=(0, 12))
        ttk.Label(row, text="Parity").pack(side="left", padx=(0, 8))
        self.parity = tk.StringVar(value="E")
        ttk.Combobox(row, textvariable=self.parity, values=["N", "E", "O"],
                     state="readonly", width=5).pack(side="left", padx=(0, 12))
        ttk.Button(row, text="Probe UART", command=self.probe_uart,
                   style="Accent.TButton").pack(side="left")
        ttk.Label(
            tab,
            text=("Use the receiver's documented serial console pins and the correct "
                  "voltage-level adapter. Never connect RS-232 voltage directly to TTL pins. "
                  "Power-cycle the receiver after starting the probe."),
            style="Sub.TLabel", wraplength=950,
        ).pack(anchor="w", pady=8)
        self.refresh_ports(quiet=True)
        return tab

    def _diagnostics_tab(self) -> ttk.Frame:
        tab = ttk.Frame(self.tabs, padding=12)
        self.tabs.add(tab, text="Diagnostics / Log")
        top = ttk.Frame(tab)
        top.pack(fill="x")
        self.selftest_btn = ttk.Button(top, text="Run self-test",
                                       command=lambda: self.run_cli(["selftest"], "Self-test"),
                                       style="Accent.TButton")
        self.selftest_btn.pack(side="left")
        ttk.Button(top, text="Clear log", command=self.clear_log).pack(side="left", padx=8)
        body = ttk.Frame(tab)
        body.pack(fill="both", expand=True, pady=(12, 0))
        scroll = ttk.Scrollbar(body, orient="vertical")
        self.output = tk.Text(body, bg="#07101d", fg="#d8e5f5",
                              insertbackground="white", wrap="word",
                              font=("Consolas", 10), relief="flat",
                              yscrollcommand=scroll.set)
        scroll.configure(command=self.output.yview)
        scroll.pack(side="right", fill="y")
        self.output.pack(side="left", fill="both", expand=True)
        self.output.configure(state="disabled")
        return tab

    # ------------------------------------------------------------------ logging
    def log(self, message: str) -> None:
        if not hasattr(self, "output"):
            return
        self.output.configure(state="normal")
        self.output.insert("end", message.rstrip() + "\n")
        self.output.see("end")
        self.output.configure(state="disabled")

    def clear_log(self) -> None:
        self.output.configure(state="normal")
        self.output.delete("1.0", "end")
        self.output.configure(state="disabled")

    def open_wizard(self) -> None:
        from skybox_recon.gui_help import SetupWizard, attach_tips
        wiz = SetupWizard(self)
        self.after(200, lambda: attach_tips(wiz))

    def call_ui(self, fn, *args) -> None:
        """Run fn(*args) on the Tk thread (safe to call from worker threads)."""
        self._calls.put((fn, args))

    def _drain_events(self) -> None:
        try:
            while True:
                fn, args = self._calls.get_nowait()
                try:
                    fn(*args)
                except Exception:  # noqa: BLE001
                    self.log("ERROR:\n" + traceback.format_exc())
        except queue.Empty:
            pass
        """Move messages from worker threads onto the Tk thread (Tk is not thread-safe)."""
        try:
            while True:
                msg = self._events.get_nowait()
                if msg is DONE:
                    self.status.set("●  OFFLINE — receiver not connected")
                    self.log("")
                else:
                    self.log(msg)
        except queue.Empty:
            pass
        self.after(100, self._drain_events)

    def _callback_error(self, exc_type, exc, tb) -> None:
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        write_crash_log(text)
        self.log("ERROR:\n" + text)
        self.tabs.select(self.diag_tab)

    # ------------------------------------------------------------------ actions
    def run_cli(self, args: list[str], title: str) -> None:
        self.tabs.select(self.diag_tab)
        self.log(f"\n=== {title} ===")
        self.status.set(f"●  RUNNING — {title}")
        command = cli_command(args)

        def worker() -> None:
            try:
                result = subprocess.run(
                    command, cwd=APP_DIR, capture_output=True, text=True,
                    encoding="utf-8", errors="replace",
                    stdin=subprocess.DEVNULL,  # a windowed exe has no valid stdin handle
                    timeout=300, creationflags=NO_WINDOW,
                )
                output = (result.stdout or "") + (result.stderr or "")
                self._events.put(output or f"Completed with exit code {result.returncode}.")
                self._events.put(f"[exit code: {result.returncode}]")
            except subprocess.TimeoutExpired:
                self._events.put("ERROR: command timed out after 300 s.")
            except Exception as exc:  # noqa: BLE001 -- report everything in the log
                self._events.put(f"ERROR: {type(exc).__name__}: {exc}")
            finally:
                self._events.put(DONE)

        threading.Thread(target=worker, daemon=True).start()

    def refresh_ports(self, quiet: bool = False) -> None:
        try:
            from serial.tools import list_ports  # optional dependency
            ports = sorted(p.device for p in list_ports.comports())
        except Exception:  # noqa: BLE001
            ports = []
        self.port_box.configure(values=ports)
        if ports and self.port.get() not in ports:
            self.port.set(ports[0])
        if not quiet:
            self.log("Serial ports: " + (", ".join(ports) if ports else "none detected"))

    def choose_firmware(self) -> None:
        path = filedialog.askopenfilename(
            title="Select receiver firmware image",
            filetypes=[("Firmware / binary", "*.bin *.img *.rom *.abs"), ("All files", "*.*")],
        )
        if path:
            self.fw_path.set(path)
            self.tabs.select(self.fw_tab)

    def analyze_firmware(self) -> None:
        path = self.fw_path.get().strip()
        if not path or not os.path.isfile(path):
            messagebox.showwarning("Select image", "Choose a firmware image first.")
            return
        out = os.path.join(os.path.dirname(path), "skybox_carved")
        self.run_cli(["fw", path, "--carve", "--extract", out], "Firmware analysis")

    def probe_uart(self) -> None:
        port = self.port.get().strip()
        if not port:
            messagebox.showwarning("Select port", "Enter or choose a serial port first.")
            return
        self.run_cli(["uart", port, "--parity", self.parity.get()], "UART probe")

    @staticmethod
    def open_path(path: str) -> None:
        try:
            if sys.platform == "win32":
                os.startfile(path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Open folder", f"Could not open {path}:\n{exc}")


def show_fatal(text: str) -> None:
    """Never let the program vanish silently: log to file and show a dialog."""
    path = write_crash_log(text)
    try:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "Skybox Recon startup error",
            text[-1500:] + (f"\n\nDetails saved to:\n{path}" if path else ""),
        )
        root.destroy()
    except Exception:  # noqa: BLE001
        if sys.stderr:
            print(text, file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["--cli"]:
        return run_engine_inline(argv[1:])
    try:
        app = SkyboxGUI(smoke=argv[:1] == ["--smoke-test"])
        if argv[:1] == ["--smoke-test"]:
            app.after(1500, app.destroy)
        app.mainloop()
        return 0
    except Exception:  # noqa: BLE001
        show_fatal(traceback.format_exc())
        return 1


if __name__ == "__main__":
    sys.exit(main())
