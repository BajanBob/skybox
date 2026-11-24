from __future__ import annotations
import os, sys, threading, subprocess, tkinter as tk
from tkinter import ttk, filedialog, messagebox

APP_TITLE = "SKYBOX RECON — Control Centre"
ROOT = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
CLI = os.path.join(ROOT, "skybox.py")

class SkyboxGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1180x780")
        self.minsize(980, 650)
        self.configure(bg="#0b1220")
        self._style()
        self._build()
        self.run_cli(["--version"], "Startup check")

    def _style(self):
        s = ttk.Style(self)
        try: s.theme_use("clam")
        except tk.TclError: pass
        s.configure(".", font=("Segoe UI", 10))
        s.configure("TFrame", background="#101a2b")
        s.configure("Panel.TFrame", background="#142238")
        s.configure("TLabel", background="#101a2b", foreground="#e6edf7")
        s.configure("Title.TLabel", font=("Segoe UI", 21, "bold"), foreground="#f4f8ff")
        s.configure("Sub.TLabel", foreground="#9fb2cc")
        s.configure("TButton", padding=8)
        s.configure("Accent.TButton", background="#1677d2", foreground="white")
        s.configure("TNotebook", background="#0b1220", borderwidth=0)
        s.configure("TNotebook.Tab", padding=(16, 9), background="#1a2b43", foreground="#dce8f8")
        s.map("TNotebook.Tab", background=[("selected", "#1677d2")], foreground=[("selected", "white")])
        s.configure("TEntry", fieldbackground="#f4f7fb")
        s.configure("TCombobox", fieldbackground="#f4f7fb")

    def _build(self):
        header = ttk.Frame(self, padding=(20, 16))
        header.pack(fill="x")
        ttk.Label(header, text="◉  SKYBOX RECON", style="Title.TLabel").pack(side="left")
        ttk.Label(header, text="ALi M3510 / M3510A RECEIVER TOOLKIT", style="Sub.TLabel").pack(side="left", padx=18, pady=(8,0))
        self.status = tk.StringVar(value="●  OFFLINE — receiver not connected")
        ttk.Label(header, textvariable=self.status, foreground="#f5c451", background="#101a2b").pack(side="right", pady=8)

        summary = ttk.Frame(self, padding=(20, 0, 20, 14))
        summary.pack(fill="x")
        for title, value in [
            ("RECEIVER", "Not connected"),
            ("CONTROL MODE", "Local / offline"),
            ("HARDWARE WRITE", "Confirmation required"),
            ("APPLICATION", "GUI preview build"),
        ]:
            card = ttk.Frame(summary, style="Panel.TFrame", padding=12)
            card.pack(side="left", fill="x", expand=True, padx=(0,10))
            tk.Label(card, text=title, bg="#142238", fg="#83a9d6", font=("Segoe UI",8,"bold")).pack(anchor="w")
            tk.Label(card, text=value, bg="#142238", fg="#f4f8ff", font=("Segoe UI",11,"bold")).pack(anchor="w", pady=(4,0))

        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill="both", expand=True, padx=20, pady=(0,12))
        self.dashboard = ttk.Frame(self.tabs, padding=18)
        self.tabs.add(self.dashboard, text="Overview")
        self._overview()
        self._firmware_tab()
        self._serial_tab()
        self._tuning_tab()
        self._diagnostics_tab()

        footer = ttk.Frame(self, padding=(20, 4, 20, 12))
        footer.pack(fill="x")
        ttk.Label(footer, text="Skybox Recon V2 • GUI shell around the existing CLI engine • Hardware features require compatible interfaces/drivers",
                  style="Sub.TLabel").pack(side="left")
        ttk.Button(footer, text="Open project folder", command=lambda: self.open_path(ROOT)).pack(side="right")

    def _overview(self):
        ttk.Label(self.dashboard, text="Receiver control centre", style="Title.TLabel").pack(anchor="w")
        ttk.Label(self.dashboard, text="Launch offline diagnostics and supported analysis tools from one persistent Windows window.",
                  style="Sub.TLabel").pack(anchor="w", pady=(4,18))
        grid = ttk.Frame(self.dashboard)
        grid.pack(fill="x")
        items = [
            ("Diagnostics", "Run the built-in offline test suite.", lambda: self.run_cli(["selftest"], "Self-test")),
            ("Firmware analysis", "Inspect a firmware image and identify known regions.", lambda: self.choose_firmware()),
            ("Serial console", "Probe a selected COM port for receiver boot output.", lambda: self.tabs.select(2)),
            ("Satellite tuning", "Prepare a tuning command for a supported DVB frontend.", lambda: self.tabs.select(3)),
        ]
        for i,(title,desc,cmd) in enumerate(items):
            panel=ttk.Frame(grid,style="Panel.TFrame",padding=16)
            panel.grid(row=i//2,column=i%2,sticky="nsew",padx=6,pady=6)
            grid.columnconfigure(i%2,weight=1)
            tk.Label(panel,text=title,bg="#142238",fg="#f4f8ff",font=("Segoe UI",14,"bold")).pack(anchor="w")
            tk.Label(panel,text=desc,bg="#142238",fg="#9fb2cc",wraplength=390,justify="left").pack(anchor="w",pady=8)
            ttk.Button(panel,text="Open",command=cmd,style="Accent.TButton").pack(anchor="w")
        note = tk.Label(self.dashboard, text="IMPORTANT: Blind scan, live spectrum/waterfall, video/audio decoding and independent dual-tuner control are not implemented by this GUI shell. The interface does not imply hardware support that has not been verified.",
                        bg="#3a2b16",fg="#ffd78a",wraplength=1000,justify="left",padx=12,pady=12)
        note.pack(fill="x",pady=(18,0))

    def _firmware_tab(self):
        tab=ttk.Frame(self.tabs,padding=18); self.tabs.add(tab,text="Firmware Lab")
        ttk.Label(tab,text="Firmware image analysis",style="Title.TLabel").pack(anchor="w")
        row=ttk.Frame(tab); row.pack(fill="x",pady=12)
        self.fw_path=tk.StringVar()
        ttk.Entry(row,textvariable=self.fw_path).pack(side="left",fill="x",expand=True,padx=(0,8))
        ttk.Button(row,text="Browse…",command=self.choose_firmware).pack(side="left")
        ttk.Button(tab,text="Analyze image",command=self.analyze_firmware,style="Accent.TButton").pack(anchor="w")
        ttk.Label(tab,text="Analysis is read-only. Firmware flashing is deliberately not exposed in this first GUI build.",style="Sub.TLabel").pack(anchor="w",pady=10)

    def _serial_tab(self):
        tab=ttk.Frame(self.tabs,padding=18); self.tabs.add(tab,text="Serial / UART")
        ttk.Label(tab,text="Serial console discovery",style="Title.TLabel").pack(anchor="w")
        row=ttk.Frame(tab); row.pack(anchor="w",pady=14)
        ttk.Label(row,text="COM port").pack(side="left",padx=(0,8))
        self.port=tk.StringVar(value="COM3")
        ttk.Entry(row,textvariable=self.port,width=16).pack(side="left",padx=(0,12))
        ttk.Label(row,text="Parity").pack(side="left",padx=(0,8))
        self.parity=tk.StringVar(value="E")
        ttk.Combobox(row,textvariable=self.parity,values=["N","E","O"],state="readonly",width=5).pack(side="left",padx=(0,12))
        ttk.Button(row,text="Probe UART",command=self.probe_uart,style="Accent.TButton").pack(side="left")
        ttk.Label(tab,text="Connect only to the receiver's documented serial console pins using the correct voltage-level adapter. Do not connect RS-232 voltage directly to TTL pins.",style="Sub.TLabel",wraplength=950).pack(anchor="w",pady=8)

    def _tuning_tab(self):
        tab=ttk.Frame(self.tabs,padding=18); self.tabs.add(tab,text="Satellite Tuning")
        ttk.Label(tab,text="DVB tuning command builder",style="Title.TLabel").pack(anchor="w")
        form=ttk.Frame(tab); form.pack(anchor="w",pady=12)
        self.freq=tk.StringVar(value="11500000"); self.sr=tk.StringVar(value="27500000")
        self.mod=tk.StringVar(value="auto"); self.delsys=tk.StringVar(value="DVBS2"); self.pol=tk.StringVar(value="H")
        fields=[("Frequency (kHz)",self.freq),("Symbol rate (sym/s)",self.sr)]
        for r,(label,var) in enumerate(fields):
            ttk.Label(form,text=label).grid(row=r,column=0,sticky="w",padx=6,pady=6)
            ttk.Entry(form,textvariable=var,width=22).grid(row=r,column=1,sticky="w",padx=6,pady=6)
        ttk.Label(form,text="Standard").grid(row=0,column=2,padx=6)
        ttk.Combobox(form,textvariable=self.delsys,values=["DVBS","DVBS2","DVBS2X"],state="readonly",width=10).grid(row=0,column=3)
        ttk.Label(form,text="Modulation").grid(row=1,column=2,padx=6)
        ttk.Combobox(form,textvariable=self.mod,values=["auto","QPSK","8PSK","16APSK","32APSK"],state="readonly",width=10).grid(row=1,column=3)
        ttk.Label(form,text="Polarization").grid(row=2,column=0,sticky="w",padx=6,pady=6)
        ttk.Combobox(form,textvariable=self.pol,values=["H","V"],state="readonly",width=8).grid(row=2,column=1,sticky="w",padx=6,pady=6)
        ttk.Button(tab,text="Show tuning command",command=self.show_tune,style="Accent.TButton").pack(anchor="w",pady=8)
        ttk.Label(tab,text="Actual tuning depends on Linux DVB utilities and compatible frontend hardware; Windows GUI does not provide a DVB driver by itself.",style="Sub.TLabel").pack(anchor="w",pady=8)

    def _diagnostics_tab(self):
        tab=ttk.Frame(self.tabs,padding=12); self.tabs.add(tab,text="Diagnostics / Log")
        top=ttk.Frame(tab); top.pack(fill="x")
        ttk.Button(top,text="Run self-test",command=lambda:self.run_cli(["selftest"],"Self-test"),style="Accent.TButton").pack(side="left")
        ttk.Button(top,text="Clear log",command=self.clear_log).pack(side="left",padx=8)
        self.output=tk.Text(tab,bg="#07101d",fg="#d8e5f5",insertbackground="white",wrap="word",font=("Consolas",10),relief="flat")
        self.output.pack(fill="both",expand=True,pady=(12,0))
        self.output.insert("end","Skybox Recon V2 GUI initialized.\nChoose a tool or run the offline self-test.\n\n")
        self.output.configure(state="disabled")

    def log(self,text):
        self.output.configure(state="normal")
        self.output.insert("end",text.rstrip()+"\n")
        self.output.see("end")
        self.output.configure(state="disabled")

    def clear_log(self):
        self.output.configure(state="normal"); self.output.delete("1.0","end"); self.output.configure(state="disabled")

    def run_cli(self,args,title):
        self.tabs.select(4)
        self.log(f"\n=== {title} ===")
        def worker():
            try:
                p=subprocess.run([*CLI_PREFIX,*args],cwd=ROOT,capture_output=True,text=True,timeout=300)
                out=(p.stdout or "")+(p.stderr or "")
                self.after(0,self.log,out if out else f"Completed with exit code {p.returncode}.")
                self.after(0,self.log,f"[exit code: {p.returncode}]")
            except Exception as e:
                self.after(0,self.log,f"ERROR: {e}")
        threading.Thread(target=worker,daemon=True).start()

    def choose_firmware(self):
        path=filedialog.askopenfilename(title="Select receiver firmware image",filetypes=[("Firmware / binary","*.bin *.img *.rom *.abs"),("All files","*.*")])
        if path:
            self.fw_path.set(path)
            self.tabs.select(1)

    def analyze_firmware(self):
        path=self.fw_path.get().strip()
        if not path or not os.path.isfile(path):
            messagebox.showwarning("Select image","Choose a firmware image first."); return
        self.run_cli(["fw",path,"--carve","--extract",os.path.join(os.path.dirname(path),"skybox_carved")],"Firmware analysis")

    def probe_uart(self):
        port=self.port.get().strip()
        if not port: return
        self.run_cli(["uart",port,"--parity",self.parity.get()],"UART probe")

    def show_tune(self):
        try: int(self.freq.get()); int(self.sr.get())
        except ValueError:
            messagebox.showerror("Invalid values","Frequency and symbol rate must be integers."); return
        args=["tune","--freq",self.freq.get(),"--sr",self.sr.get(),"--delsys",self.delsys.get(),"--mod",self.mod.get(),"--pol",self.pol.get()]
        self.tabs.select(4)
        self.log("\nPrepared command (not executed):\n"+subprocess.list2cmdline([*CLI_PREFIX,*args]))
        self.log("Tuning is not started from this Windows GUI. Use a compatible DVB frontend environment.")

    def open_path(self,path):
        if sys.platform=="win32": os.startfile(path)
        elif sys.platform=="darwin": subprocess.Popen(["open",path])
        else: subprocess.Popen(["xdg-open",path])

if __name__=="__main__":
    SkyboxGUI().mainloop()
