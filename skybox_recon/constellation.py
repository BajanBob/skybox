"""PSK constellation recovery and MER from complex IQ captures.

Pipeline: DC removal -> resample to 4 samples/symbol -> coarse carrier offset
from the M-th power spectrum -> RRC matched filter -> symbol timing (max
energy phase per block) -> block-wise M-th power carrier phase -> MER.
Works for QPSK and 8PSK carriers that fit inside the SDR's sample rate
(RTL-SDR ~2.4 MS/s, HackRF up to 20 MS/s), e.g. low-symbol-rate feeds.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


def rrc_taps(sps: int, beta: float, span: int) -> np.ndarray:
    n = np.arange(-span * sps, span * sps + 1) / sps
    taps = np.zeros_like(n)
    for i, t in enumerate(n):
        if abs(t) < 1e-9:
            taps[i] = 1 - beta + 4 * beta / np.pi
        elif beta > 0 and abs(abs(4 * beta * t) - 1) < 1e-9:
            taps[i] = beta / np.sqrt(2) * ((1 + 2 / np.pi) * np.sin(np.pi / (4 * beta))
                                           + (1 - 2 / np.pi) * np.cos(np.pi / (4 * beta)))
        else:
            taps[i] = (np.sin(np.pi * t * (1 - beta)) + 4 * beta * t * np.cos(np.pi * t * (1 + beta))) / (
                np.pi * t * (1 - (4 * beta * t) ** 2))
    return taps / np.sqrt(np.sum(taps ** 2))


def load_iq(path: str, fmt: str = "auto", max_samples: int = 2_000_000) -> np.ndarray:
    """cu8 = rtl_sdr, cs8 = hackrf_transfer, cf32 = GNU Radio / SDR# complex float."""
    if fmt == "auto":
        low = path.lower()
        fmt = "cs8" if low.endswith((".cs8", ".iq8")) else "cf32" if low.endswith((".cf32", ".fc32", ".cfile")) else "cu8"
    if fmt == "cu8":
        raw = np.fromfile(path, dtype=np.uint8, count=2 * max_samples).astype(np.float32)
        raw = (raw - 127.5) / 128.0
    elif fmt == "cs8":
        raw = np.fromfile(path, dtype=np.int8, count=2 * max_samples).astype(np.float32) / 128.0
    elif fmt == "cf32":
        raw = np.fromfile(path, dtype=np.float32, count=2 * max_samples)
    else:
        raise ValueError("format must be cu8, cs8 or cf32")
    raw = raw[: raw.size // 2 * 2]
    return raw[0::2] + 1j * raw[1::2]


@dataclass
class ConstellationResult:
    symbols: np.ndarray
    mer_db: float
    freq_offset_hz: float
    order: int
    evm_pct: float


def _resample(x: np.ndarray, factor: float) -> np.ndarray:
    if abs(factor - 1) < 1e-9:
        return x
    n_out = int(x.size * factor)
    t_out = np.arange(n_out) / factor
    t_in = np.arange(x.size)
    return np.interp(t_out, t_in, x.real) + 1j * np.interp(t_out, t_in, x.imag)


def recover(iq: np.ndarray, sample_rate: float, symbol_rate: float, order: int = 4,
            rolloff: float = 0.35, block: int = 128) -> ConstellationResult:
    if order not in (2, 4, 8):
        raise ValueError("order must be 2 (BPSK), 4 (QPSK) or 8 (8PSK)")
    sps_in = sample_rate / symbol_rate
    if sps_in < 1.5:
        raise ValueError(f"sample rate must be at least 1.5x the symbol rate (got {sps_in:.2f}x)")
    x = np.asarray(iq, complex)
    x = x - x.mean()
    sps = 4
    x = _resample(x, sps / sps_in)
    x /= np.sqrt(np.mean(np.abs(x) ** 2)) or 1.0
    # coarse carrier: the M-th power removes PSK modulation, leaving a tone at M*f
    nfft = 1 << int(np.ceil(np.log2(min(x.size, 1 << 18))))
    spec = np.abs(np.fft.fft(x[:nfft] ** order, nfft))
    k = int(np.argmax(spec))
    f_norm = (k if k < nfft / 2 else k - nfft) / nfft / order
    n = np.arange(x.size)
    x = x * np.exp(-2j * np.pi * f_norm * n)
    y = np.convolve(x, rrc_taps(sps, rolloff, 8), mode="same")
    nsym = y.size // sps
    out = []
    for b in range(0, nsym - block + 1, block):
        seg = y[b * sps:(b + block) * sps]
        phase = int(np.argmax([np.mean(np.abs(seg[p::sps]) ** 2) for p in range(sps)]))
        out.append(seg[phase::sps][:block])
    if not out:
        raise ValueError("capture too short for the requested symbol rate")
    # block-wise carrier phase with unwrapping across blocks
    phases = np.array([np.angle(np.mean(s ** order)) / order for s in out])
    phases = np.unwrap(phases * order) / order
    offset = np.pi / order if order in (4,) else 0.0
    syms = np.concatenate([s * np.exp(-1j * (ph - offset)) for s, ph in zip(out, phases)])
    syms /= np.mean(np.abs(syms)) or 1.0
    ideal_angles = np.round((np.angle(syms) - offset) / (2 * np.pi / order)) * (2 * np.pi / order) + offset
    ideal = np.exp(1j * ideal_angles)
    err = syms - ideal
    mer = 10 * np.log10(np.mean(np.abs(ideal) ** 2) / max(np.mean(np.abs(err) ** 2), 1e-12))
    evm = 100 * np.sqrt(np.mean(np.abs(err) ** 2))
    return ConstellationResult(syms, float(mer), float(f_norm * symbol_rate * sps),
                               order, float(evm))


def capture_command(tool: str, centre_hz: int, sample_rate: int, seconds: float, out_path: str,
                    gain: int = 30) -> list[str]:
    n = int(sample_rate * seconds)
    if tool == "rtl_sdr":
        return ["rtl_sdr", "-f", str(centre_hz), "-s", str(sample_rate), "-g", str(gain), "-n", str(n), out_path]
    if tool == "hackrf_transfer":
        return ["hackrf_transfer", "-r", out_path, "-f", str(centre_hz), "-s", str(sample_rate),
                "-n", str(n), "-l", "32", "-g", str(min(62, gain))]
    raise ValueError("tool must be rtl_sdr or hackrf_transfer")
