"""Auto-detection of connected USB hardware (SDRs and USB-serial adapters).

Works on Windows, Linux and macOS without extra drivers or admin rights:

* Windows  - PowerShell/CIM query of present PnP devices (also reports which driver
             is bound, so we can tell the user when Zadig/WinUSB is still needed).
* Linux    - /sys/bus/usb/devices (idVendor/idProduct, bound driver).
* macOS    - ``system_profiler SPUSBDataType -json``.
* Serial   - pyserial ``list_ports`` everywhere (optional dependency).

RTL-SDR dongles all share one USB ID, so the tuner chip (R820T vs E4000) is read
from ``rtl_test -t`` when that tool is installed.
"""
from __future__ import annotations

import glob
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field

NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

# (vid, pid or None for any) -> (kind, friendly name, SDRS key or None)
KNOWN: dict[tuple[str, str | None], tuple[str, str, str | None]] = {
    ("0bda", "2838"): ("sdr", "RTL-SDR (RTL2832U)", "RTL-SDR R820T2 / R828D (e.g. NESDR Nano 3, RTL-SDR Blog V3/V4)"),
    ("0bda", "2832"): ("sdr", "RTL-SDR (RTL2832U)", "RTL-SDR R820T2 / R828D (e.g. NESDR Nano 3, RTL-SDR Blog V3/V4)"),
    ("1d50", "6089"): ("sdr", "HackRF One", "HackRF One"),
    ("1d50", "cc15"): ("sdr", "HackRF (rad1o)", "HackRF One"),
    ("2cf0", "5250"): ("sdr", "Nuand bladeRF 2.0", None),
    ("2cf0", "5246"): ("sdr", "Nuand bladeRF", None),
    ("1d50", "60a1"): ("sdr", "Airspy", None),
    ("03eb", "800c"): ("sdr", "Airspy HF+", None),
    ("1df7", None): ("sdr", "SDRplay RSP", None),
    ("2500", None): ("sdr", "Ettus USRP", None),
    ("303a", None): ("serial", "Espressif ESP32 (native USB)", None),
    ("10c4", "ea60"): ("serial", "Silicon Labs CP210x USB-UART", None),
    ("1a86", "7523"): ("serial", "WCH CH340 USB-UART", None),
    ("1a86", "55d4"): ("serial", "WCH CH9102 USB-UART", None),
    ("0403", None): ("serial", "FTDI USB-UART", None),
    ("067b", "2303"): ("serial", "Prolific PL2303 USB-UART", None),
}

E4000_KEY = "RTL-SDR E4000 (e.g. NESDR SMArTee XTR)"


@dataclass
class Device:
    kind: str                 # "sdr" or "serial"
    name: str
    vid: str
    pid: str
    sdr_key: str | None = None
    port: str | None = None   # serial port (COM5, /dev/ttyUSB0 ...)
    driver: str = ""          # bound driver/service when known
    problem: str = ""         # user-facing hint when it will not work yet
    extra: dict = field(default_factory=dict)

    @property
    def ident(self) -> str:
        return f"{self.vid}:{self.pid}:{self.port or ''}"

    def label(self) -> str:
        s = self.name + (f" on {self.port}" if self.port else "")
        return s + (f" — {self.problem}" if self.problem else "")


def lookup(vid: str, pid: str):
    vid, pid = vid.lower(), pid.lower()
    return KNOWN.get((vid, pid)) or KNOWN.get((vid, None))


def _run(cmd: list[str], timeout: float = 8) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           stdin=subprocess.DEVNULL, creationflags=NO_WINDOW)
        return (r.stdout or "") + (r.stderr or "")
    except Exception:  # noqa: BLE001
        return ""


# ---------------------------------------------------------------- raw USB scans
def _scan_windows() -> list[tuple[str, str, str]]:
    """Return (vid, pid, service) for present devices."""
    ps = ("Get-CimInstance Win32_PnPEntity | Where-Object { $_.PNPDeviceID -like 'USB\\VID_*' } | "
          "ForEach-Object { $_.PNPDeviceID + '|' + $_.Service }")
    out = _run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], timeout=15)
    found = []
    for line in out.splitlines():
        m = re.search(r"VID_([0-9A-Fa-f]{4})&PID_([0-9A-Fa-f]{4})", line)
        if m:
            found.append((m.group(1).lower(), m.group(2).lower(), line.split("|")[-1].strip()))
    return found


def _scan_linux() -> list[tuple[str, str, str]]:
    found = []
    for d in glob.glob("/sys/bus/usb/devices/*"):
        try:
            vid = open(os.path.join(d, "idVendor")).read().strip()
            pid = open(os.path.join(d, "idProduct")).read().strip()
        except OSError:
            continue
        drivers = set()
        for intf in glob.glob(d + "/*:*/driver"):
            drivers.add(os.path.basename(os.path.realpath(intf)))
        found.append((vid, pid, ",".join(sorted(drivers))))
    return found


def _scan_macos() -> list[tuple[str, str, str]]:
    out = _run(["system_profiler", "SPUSBDataType", "-json"], timeout=15)
    found = []
    try:
        data = json.loads(out)
    except ValueError:
        return found

    def walk(items):
        for it in items or []:
            v, p = str(it.get("vendor_id", "")), str(it.get("product_id", ""))
            mv, mp = re.search(r"0x([0-9a-f]{4})", v), re.search(r"0x([0-9a-f]{4})", p)
            if mv and mp:
                found.append((mv.group(1), mp.group(1), ""))
            walk(it.get("_items"))
    walk(data.get("SPUSBDataType"))
    return found


def scan_usb() -> list[tuple[str, str, str]]:
    if sys.platform == "win32":
        return _scan_windows()
    if sys.platform == "darwin":
        return _scan_macos()
    return _scan_linux()


def scan_serial() -> list[Device]:
    try:
        from serial.tools import list_ports
    except Exception:  # noqa: BLE001
        return []
    out = []
    for p in list_ports.comports():
        if p.vid is None:
            continue
        vid, pid = f"{p.vid:04x}", f"{p.pid:04x}"
        k = lookup(vid, pid)
        name = k[1] if k and k[0] == "serial" else (p.description or "USB serial device")
        out.append(Device("serial", name, vid, pid, port=p.device))
    return out


def rtl_tuner() -> str | None:
    """Read the tuner chip from rtl_test (only if installed). Returns an SDRS key."""
    exe = shutil.which("rtl_test")
    if not exe:
        return None
    try:
        p = subprocess.Popen([exe, "-t"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                             stdin=subprocess.DEVNULL, creationflags=NO_WINDOW)
        out, _ = p.communicate(timeout=6)
    except subprocess.TimeoutExpired:
        p.kill(); out = p.communicate()[0] or ""
    except Exception:  # noqa: BLE001
        return None
    if "E4000" in out:
        return E4000_KEY
    if re.search(r"R8[12]\d", out):
        return KNOWN[("0bda", "2838")][2]
    return None


def detect(probe_tuner: bool = True) -> list[Device]:
    """Everything useful that is plugged in right now."""
    devices: list[Device] = []
    seen = set()
    for vid, pid, drv in scan_usb():
        k = lookup(vid, pid)
        if not k or k[0] != "sdr" or (vid, pid) in seen:
            continue
        seen.add((vid, pid))
        d = Device("sdr", k[1], vid, pid, sdr_key=k[2], driver=drv)
        if vid == "0bda":
            if sys.platform == "win32" and drv and drv.lower() not in ("winusb", "libusbk", "libusb0"):
                d.problem = "driver is not WinUSB yet: run Zadig (Options → List All Devices → Interface 0 → WinUSB)"
            elif sys.platform.startswith("linux") and "dvb_usb_rtl28xxu" in drv:
                d.problem = "the Linux TV driver holds it: blacklist dvb_usb_rtl28xxu or unplug/replug after 'sudo rmmod dvb_usb_rtl28xxu'"
            elif probe_tuner:
                d.sdr_key = rtl_tuner() or d.sdr_key
        devices.append(d)
    devices += scan_serial()
    return devices


def best_sdr(devices: list[Device]) -> Device | None:
    order = ["HackRF One", "RTL-SDR"]
    sdrs = [d for d in devices if d.kind == "sdr" and d.sdr_key]
    for name in order:
        for d in sdrs:
            if d.name.startswith(name):
                return d
    return sdrs[0] if sdrs else None


def best_serial(devices: list[Device]) -> str | None:
    ser = [d for d in devices if d.kind == "serial" and d.port]
    # prefer real USB-UART bridges (receiver console) over ESP32 native USB
    ser.sort(key=lambda d: (d.vid == "303a", d.port))
    return ser[0].port if ser else None


def summary(devices: list[Device]) -> str:
    if not devices:
        return "No SDR or USB-serial adapter detected"
    return " • ".join(d.label() for d in devices)
