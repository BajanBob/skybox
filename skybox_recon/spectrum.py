"""L-band spectrum sweeps, blind-scan transponder detection and the
satellite-finder tone.

Live sweeps come from rtl_power (RTL-SDR) or hackrf_sweep (HackRF One); both
print the same CSV shape: date, time, Hz low, Hz high, Hz step, samples, dB...
The dish's LNB must be powered (13/18 V) by a receiver or a power inserter.
"""
from __future__ import annotations

import math
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import wave
from dataclasses import dataclass

from .dvb import IF_MAX_MHZ, IF_MIN_MHZ, if_to_rf

# --------------------------------------------------------------------------- #
# sweep sources
# --------------------------------------------------------------------------- #

SOURCES = ("rtl_power", "hackrf_sweep")


def sweep_command(tool: str, start_mhz: float = IF_MIN_MHZ, stop_mhz: float = IF_MAX_MHZ,
                  bin_khz: int = 1000, gain: int = 30, once: bool = False) -> list[str]:
    if tool == "rtl_power":
        cmd = ["rtl_power", "-f", f"{start_mhz:g}M:{stop_mhz:g}M:{bin_khz}k", "-i", "1",
               "-g", str(gain)]
        return cmd + (["-1"] if once else []) + ["-"]
    if tool == "hackrf_sweep":
        cmd = ["hackrf_sweep", "-f", f"{int(start_mhz)}:{int(math.ceil(stop_mhz))}",
               "-w", str(bin_khz * 1000), "-l", "32", "-g", str(min(62, gain))]
        return cmd + (["-1"] if once else [])
    raise ValueError(f"unknown sweep tool {tool}")


def tool_available(tool: str) -> bool:
    return shutil.which(tool) is not None


def parse_csv_line(line: str) -> tuple[str, list[float], list[float]] | None:
    parts = [p.strip() for p in line.split(",")]
    if len(parts) < 7:
        return None
    try:
        lo, step = float(parts[2]), float(parts[4])
        levels = [float(v) for v in parts[6:] if v and v.lower() != "nan"]
    except ValueError:
        return None
    if step <= 0:
        return None
    freqs = [(lo + step * (i + 0.5)) / 1e6 for i in range(len(levels))]
    return f"{parts[0]} {parts[1]}", freqs, levels


class SweepAssembler:
    """Collects CSV rows into whole sweeps (a sweep ends when frequency wraps)."""

    def __init__(self) -> None:
        self._f: list[float] = []
        self._l: list[float] = []
        self._last_lo = -1.0

    def feed(self, line: str) -> tuple[list[float], list[float]] | None:
        row = parse_csv_line(line)
        if row is None:
            return None
        _, freqs, levels = row
        done = None
        if freqs and freqs[0] < self._last_lo and self._f:
            done = self.flush()
        if freqs:
            self._last_lo = freqs[0]
        self._f += freqs
        self._l += levels
        return done

    def flush(self) -> tuple[list[float], list[float]] | None:
        if not self._f:
            return None
        pairs = sorted(zip(self._f, self._l))
        self._f, self._l, self._last_lo = [], [], -1.0
        return [p[0] for p in pairs], [p[1] for p in pairs]


def read_sweeps_csv(text: str) -> list[tuple[list[float], list[float]]]:
    asm, out = SweepAssembler(), []
    for line in text.splitlines():
        s = asm.feed(line)
        if s:
            out.append(s)
    last = asm.flush()
    if last:
        out.append(last)
    return out


class LiveSweep:
    """Runs an SDR sweep tool and hands each completed sweep to a callback."""

    def __init__(self, cmd: list[str], on_sweep, on_error=None) -> None:
        self.cmd, self.on_sweep, self.on_error = cmd, on_sweep, on_error
        self.proc: subprocess.Popen | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
        self.proc = subprocess.Popen(self.cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     stdin=subprocess.DEVNULL, text=True, bufsize=1, creationflags=flags)
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        asm = SweepAssembler()
        assert self.proc and self.proc.stdout
        for line in self.proc.stdout:
            s = asm.feed(line)
            if s:
                self.on_sweep(*s)
        last = asm.flush()
        if last:
            self.on_sweep(*last)
        code = self.proc.wait()
        if code not in (0, None, -15, 1) and self.on_error:
            err = (self.proc.stderr.read() if self.proc.stderr else "")[-400:]
            self.on_error(f"{self.cmd[0]} exited with code {code}. {err}")

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()


# --------------------------------------------------------------------------- #
# analysis
# --------------------------------------------------------------------------- #

def noise_floor(levels: list[float]) -> float:
    s = sorted(levels)
    return s[len(s) // 4] if s else 0.0   # 25th percentile: robust with many carriers


def smooth(levels: list[float], width: int = 3) -> list[float]:
    if width <= 1 or len(levels) < width:
        return list(levels)
    h = width // 2
    out = []
    for i in range(len(levels)):
        win = levels[max(0, i - h):i + h + 1]
        out.append(sum(win) / len(win))
    return out


@dataclass
class Transponder:
    if_mhz: float
    rf_mhz: float
    bandwidth_mhz: float
    sr_ksym: int               # estimated from the -3 dB bandwidth
    level_db: float
    snr_db: float              # peak above noise floor (a C/N estimate)
    pol: str = "?"

    def label(self) -> str:
        if self.rf_mhz == self.if_mhz:
            return (f"{self.rf_mhz:9.3f} MHz {self.pol}  "
                    f"~{self.sr_ksym:>6} ksym/s  C/N {self.snr_db:4.1f} dB")
        return (f"{self.rf_mhz:9.1f} MHz {self.pol}  (IF {self.if_mhz:7.1f})  "
                f"~{self.sr_ksym:>6} ksym/s  C/N {self.snr_db:4.1f} dB")


def detect_transponders(freqs: list[float], levels: list[float], lof_mhz: float = 9750.0,
                        pol: str = "?", threshold_db: float = 3.0, min_bw_mhz: float | None = None,
                        max_bw_mhz: float = 72.0, min_sr_ksym: int = 100,
                        max_sr_ksym: int = 72000) -> list[Transponder]:
    """Spectral blind scan: carriers that rise threshold_db above the floor.

    For a raised-cosine DVB carrier the -3 dB bandwidth equals the symbol rate,
    so the estimate is within one sweep bin of the true value.
    """
    if len(freqs) < 3:
        return []
    step = (freqs[-1] - freqs[0]) / (len(freqs) - 1)
    if min_bw_mhz is None:
        min_bw_mhz = 2.5 * step        # wider than a noise spike (1-2 bins)
    lv = smooth(levels, 3)
    floor = noise_floor(lv)
    found: list[Transponder] = []
    i, n = 0, len(lv)
    while i < n:
        if lv[i] < floor + threshold_db:
            i += 1
            continue
        j = i
        while j + 1 < n and lv[j + 1] >= floor + threshold_db:
            j += 1
        seg = range(i, j + 1)
        peak_i = max(seg, key=lambda k: lv[k])
        peak = lv[peak_i]
        # -3 dB edges relative to the carrier's flat top (median of the top half)
        top = sorted(lv[k] for k in seg)[len(seg) // 2:]
        plateau = sum(top) / len(top) if top else peak
        edge = plateau - 3.0
        a, b = i, j
        while a < j and lv[a] < edge:
            a += 1
        while b > i and lv[b] < edge:
            b -= 1
        # sub-bin interpolation at each edge
        def cross(k_in: int, k_out: int) -> float:
            if not 0 <= k_out < n or lv[k_in] == lv[k_out]:
                return freqs[k_in]
            t = (lv[k_in] - edge) / (lv[k_in] - lv[k_out])
            return freqs[k_in] + (freqs[k_out] - freqs[k_in]) * max(0.0, min(1.0, t))
        f_lo, f_hi = cross(a, a - 1), cross(b, b + 1)
        bw = max(step, f_hi - f_lo)
        centre = (f_lo + f_hi) / 2
        sr = max(1, int(round(bw * 1000)))
        if min_bw_mhz <= bw <= max_bw_mhz and min_sr_ksym <= sr <= max_sr_ksym:
            found.append(Transponder(round(centre, 4), round(if_to_rf(centre, lof_mhz), 4), round(bw, 4),
                                     sr, round(peak, 1), round(peak - floor, 1), pol))
        i = j + 1
    return merge_duplicates(found)


def merge_duplicates(items: list[Transponder]) -> list[Transponder]:
    """Drop carriers whose centres fall inside a stronger neighbour's bandwidth."""
    out: list[Transponder] = []
    for t in sorted(items, key=lambda t: -t.snr_db):
        if all(abs(t.if_mhz - o.if_mhz) > max(t.bandwidth_mhz, o.bandwidth_mhz) / 2 or t.pol != o.pol for o in out):
            out.append(t)
    return sorted(out, key=lambda t: t.if_mhz)


# --------------------------------------------------------------------------- #
# satellite finder
# --------------------------------------------------------------------------- #

@dataclass
class FinderReading:
    level_db: float
    cn_db: float
    quality: float        # 0..1
    tone_hz: int
    interval_ms: int
    locked: bool
    peak_cn_db: float


class SatFinder:
    """Turns sweeps into a finder tone: higher pitch and faster beeps as the
    carrier rises above the noise floor; continuous tone at lock level."""

    def __init__(self, full_scale_db: float = 18.0, lock_db: float = 10.0,
                 window: tuple[float, float] | None = None) -> None:
        self.full_scale_db, self.lock_db, self.window = full_scale_db, lock_db, window
        self.peak = 0.0

    def reset_peak(self) -> None:
        self.peak = 0.0

    def update(self, freqs: list[float], levels: list[float]) -> FinderReading:
        if self.window:
            pairs = [(f, l) for f, l in zip(freqs, levels) if self.window[0] <= f <= self.window[1]]
            lv = [l for _, l in pairs] or levels
        else:
            lv = levels
        floor = noise_floor(levels)
        top = max(smooth(lv, 3)) if lv else floor
        cn = max(0.0, top - floor)
        self.peak = max(self.peak, cn)
        q = max(0.0, min(1.0, cn / self.full_scale_db))
        return FinderReading(round(top, 1), round(cn, 1), q, int(300 + 1500 * q),
                             int(1000 - 880 * q), cn >= self.lock_db, round(self.peak, 1))


def _wav(freq: int, ms: int, path: str, rate: int = 22050) -> None:
    n = int(rate * ms / 1000)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        fade = max(1, int(rate * 0.005))
        frames = bytearray()
        for i in range(n):
            env = min(1.0, i / fade, (n - i) / fade)
            frames += struct.pack("<h", int(12000 * env * math.sin(2 * math.pi * freq * i / rate)))
        w.writeframes(bytes(frames))


def play_tone(freq: int, ms: int) -> bool:
    """Play a short beep. Returns False if no audio path exists (GUI then rings the bell)."""
    freq = max(37, min(32767, int(freq)))
    if sys.platform == "win32":
        try:
            import winsound
            winsound.Beep(freq, ms)
            return True
        except (ImportError, RuntimeError):
            return False
    player = next((p for p in ("paplay", "aplay", "afplay", "pw-play") if shutil.which(p)), None)
    if not player:
        return False
    fd, path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    try:
        _wav(freq, ms, path)
        args = [player, path] if player != "aplay" else [player, "-q", path]
        subprocess.run(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=5)
        return True
    except (OSError, subprocess.SubprocessError):
        return False
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
