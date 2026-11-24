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
    def __init__(self) -> None:
        super().__init__()
        self._events: queue.Queue = queue.Queue()
        self.title(APP_TITLE)
        self.geometry("1180x780")
        self.minsize(980, 650)
        self.configure(bg="#0b1220")
        self.report_callback_exception = self._callback_error
        self._style()
        self._build()
        self.log("GUI started. Receiver is offline until connected.")
        self.log(f"Application folder: {APP_DIR}")
        self.log("Open Diagnostics / Log → Run self-test to check the command engine.")
        self.after(100, self._drain_events)

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
        style.configure("Title.TLabel", font=("Segoe UI", 21, "bold"), foreground="#f4f8ff")
        style.configure("Sub.TLabel", foreground="#9fb2cc")
        style.configure("Status.TLabel", foreground="#f5c451")
        style.configure("TButton", padding=8)
        style.configure("Accent.TButton", background="#1677d2", foreground="white")
        style.map("Accent.TButton", background=[("active", "#2b8be6")])
        style.configure("TNotebook", background="#0b1220", borderwidth=0)
        style.configure("TNotebook.Tab", padding=(16, 9), background="#1a2b43", foreground="#dce8f8")
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
            ("APPLICATION", "V2 desktop interface"),
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
            text="Skybox Recon V2 • Hardware functions require compatible receiver interfaces/drivers",
            style="Sub.TLabel",
        ).pack(side="left")
        ttk.Button(footer, text="Open application folder",
                   command=lambda: self.open_path(APP_DIR)).pack(side="right")

        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill="both", expand=True, padx=20, pady=(0, 12))
        self.dashboard = ttk.Frame(self.tabs, padding=18)
        self.tabs.add(self.dashboard, text="Overview")
        self._overview()
        self.fw_tab = self._firmware_tab()
        self.serial_tab = self._serial_tab()
        self.tune_tab = self._tuning_tab()
        self.diag_tab = self._diagnostics_tab()

    def _overview(self) -> None:
        ttk.Label(self.dashboard, text="Receiver control centre",
                  style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            self.dashboard,
            text="Launch diagnostics and supported analysis tools from one persistent window.",
            style="Sub.TLabel",
        ).pack(anchor="w", pady=(4, 18))
        grid = ttk.Frame(self.dashboard)
        grid.pack(fill="x")
        items = [
            ("Diagnostics", "Run the offline self-test suite.",
             lambda: self.run_cli(["selftest"], "Self-test")),
            ("Firmware analysis", "Inspect a firmware image (read-only).",
             self.choose_firmware),
            ("Serial console", "Probe a selected COM / serial port.",
             lambda: self.tabs.select(self.serial_tab)),
            ("Satellite tuning", "Prepare a DVB tuning command.",
             lambda: self.tabs.select(self.tune_tab)),
        ]
        for i, (title, desc, action) in enumerate(items):
            panel = ttk.Frame(grid, style="Panel.TFrame", padding=16)
            panel.grid(row=i // 2, column=i % 2, sticky="nsew", padx=6, pady=6)
            grid.columnconfigure(i % 2, weight=1)
            tk.Label(panel, text=title, bg="#142238", fg="#f4f8ff",
                     font=("Segoe UI", 14, "bold")).pack(anchor="w")
            tk.Label(panel, text=desc, bg="#142238", fg="#9fb2cc",
                     wraplength=390, justify="left").pack(anchor="w", pady=8)
            ttk.Button(panel, text="Open", command=action,
                       style="Accent.TButton").pack(anchor="w")
        tk.Label(
            self.dashboard,
            text=("LIMITATIONS: This GUI does not yet implement live blind scan, "
                  "spectrum acquisition, PID parsing/decoding, independent dual-tuner "
                  "drivers, or Wi-Fi AV transmission."),
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

    def _tuning_tab(self) -> ttk.Frame:
        tab = ttk.Frame(self.tabs, padding=18)
        self.tabs.add(tab, text="Satellite Tuning")
        ttk.Label(tab, text="DVB tuning command builder", style="Title.TLabel").pack(anchor="w")
        form = ttk.Frame(tab)
        form.pack(anchor="w", pady=12)
        self.freq = tk.StringVar(value="11500000")
        self.sr = tk.StringVar(value="27500000")
        self.mod = tk.StringVar(value="auto")
        self.delsys = tk.StringVar(value="DVBS2")
        self.pol = tk.StringVar(value="H")
        for row, (label, var) in enumerate([
            ("Frequency (kHz)", self.freq), ("Symbol rate (sym/s)", self.sr)
        ]):
            ttk.Label(form, text=label).grid(row=row, column=0, sticky="w", padx=6, pady=6)
            ttk.Entry(form, textvariable=var, width=22).grid(row=row, column=1,
                                                             sticky="w", padx=6, pady=6)
        ttk.Label(form, text="Standard").grid(row=0, column=2, padx=6)
        ttk.Combobox(form, textvariable=self.delsys, values=["DVBS", "DVBS2", "DVBS2X"],
                     state="readonly", width=10).grid(row=0, column=3)
        ttk.Label(form, text="Modulation").grid(row=1, column=2, padx=6)
        ttk.Combobox(form, textvariable=self.mod,
                     values=["auto", "QPSK", "8PSK", "16APSK", "32APSK"],
                     state="readonly", width=10).grid(row=1, column=3)
        ttk.Label(form, text="Polarization").grid(row=2, column=0, sticky="w", padx=6, pady=6)
        ttk.Combobox(form, textvariable=self.pol, values=["H", "V", "L", "R"],
                     state="readonly", width=8).grid(row=2, column=1, sticky="w", padx=6, pady=6)
        ttk.Button(tab, text="Show tuning command", command=self.show_tune,
                   style="Accent.TButton").pack(anchor="w", pady=8)
        ttk.Label(
            tab,
            text=("This panel prepares a command only; compatible DVB frontend hardware, "
                  "drivers and dvbv5-zap (Linux DVB tools) are required for actual tuning."),
            style="Sub.TLabel", wraplength=950,
        ).pack(anchor="w", pady=8)
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

    def _drain_events(self) -> None:
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

    def show_tune(self) -> None:
        try:
            int(self.freq.get())
            int(self.sr.get())
        except ValueError:
            messagebox.showerror("Invalid values", "Frequency and symbol rate must be whole numbers.")
            return
        args = ["tune", "--freq", self.freq.get(), "--sr", self.sr.get(),
                "--delsys", self.delsys.get(), "--mod", self.mod.get(),
                "--pol", self.pol.get()]
        self.tabs.select(self.diag_tab)
        self.log("Prepared tuning command (not executed):\n"
                 + subprocess.list2cmdline(cli_command(args)))

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
        app = SkyboxGUI()
        if argv[:1] == ["--smoke-test"]:
            app.after(1500, app.destroy)
        app.mainloop()
        return 0
    except Exception:  # noqa: BLE001
        show_fatal(traceback.format_exc())
        return 1


if __name__ == "__main__":
    sys.exit(main())
