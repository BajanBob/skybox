"""Logical dual-tuner and MPEG-TS service models for Skybox Recon.

These are hardware-independent models only. A backend must prove that each
configured tuner maps to a physically independent RF tuner/demodulator path.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class TunerState(str, Enum):
    IDLE = "idle"
    SCANNING = "scanning"
    TUNING = "tuning"
    LOCKED = "locked"
    ERROR = "error"


@dataclass(frozen=True)
class TunerCapabilities:
    backend: str
    independent_rf_path: bool
    standards: tuple[str, ...] = ("DVB-S", "DVB-S2", "DVB-S2X")
    min_symbol_rate: int | None = None
    max_symbol_rate: int | None = None
    blind_scan: bool = False
    ts_output: bool = False


@dataclass
class TunerSession:
    tuner_id: str
    capabilities: TunerCapabilities
    state: TunerState = TunerState.IDLE
    frequency_khz: int | None = None
    polarization: str | None = None
    symbol_rate: int | None = None
    modulation: str | None = None
    locked: bool = False
    snr_db: float | None = None
    mer_db: float | None = None
    ber: float | None = None
    assigned_task: str | None = None

    def validate(self) -> None:
        if self.tuner_id not in {"A", "B"}:
            raise ValueError("tuner_id must be A or B")
        if self.symbol_rate is not None and self.symbol_rate <= 0:
            raise ValueError("symbol_rate must be positive")
        if self.polarization not in {None, "H", "V", "L", "R"}:
            raise ValueError("polarization must be H, V, L, or R")


@dataclass(frozen=True)
class PIDComponent:
    pid: int
    component_type: str  # video, audio, subtitle, data, PCR, PMT, unknown
    codec: str | None = None
    language: str | None = None
    component_tag: int | None = None

    def __post_init__(self) -> None:
        if not 0 <= self.pid <= 0x1FFF:
            raise ValueError("PID must be in the MPEG-TS range 0..8191")


@dataclass(frozen=True)
class ServiceRecord:
    service_id: int
    service_name: str | None
    transport_stream_id: int | None
    original_network_id: int | None
    pmt_pid: int
    pcr_pid: int
    components: tuple[PIDComponent, ...] = field(default_factory=tuple)
    scrambled: bool | None = None

    def __post_init__(self) -> None:
        if not 0 <= self.service_id <= 0xFFFF:
            raise ValueError("service_id must be 0..65535")
        if not 0 <= self.pmt_pid <= 0x1FFF or not 0 <= self.pcr_pid <= 0x1FFF:
            raise ValueError("PMT/PCR PID must be 0..8191")

    @property
    def video_pids(self) -> tuple[int, ...]:
        return tuple(c.pid for c in self.components if c.component_type == "video")

    @property
    def audio_pids(self) -> tuple[int, ...]:
        return tuple(c.pid for c in self.components if c.component_type == "audio")


class DualTunerCoordinator:
    """Coordinates two independent backend sessions; does not create hardware."""

    def __init__(self, tuner_a: TunerSession, tuner_b: TunerSession) -> None:
        if tuner_a.tuner_id != "A" or tuner_b.tuner_id != "B":
            raise ValueError("provide tuner A followed by tuner B")
        tuner_a.validate()
        tuner_b.validate()
        if not tuner_a.capabilities.independent_rf_path or not tuner_b.capabilities.independent_rf_path:
            raise ValueError("dual independent reception requires two verified RF paths")
        self.tuners = {"A": tuner_a, "B": tuner_b}

    def assign(self, tuner_id: str, task: str) -> None:
        if tuner_id not in self.tuners:
            raise KeyError(tuner_id)
        if not task.strip():
            raise ValueError("task cannot be blank")
        self.tuners[tuner_id].assigned_task = task

    def snapshot(self) -> dict[str, dict[str, object]]:
        return {
            key: {
                "state": tuner.state.value,
                "locked": tuner.locked,
                "frequency_khz": tuner.frequency_khz,
                "symbol_rate": tuner.symbol_rate,
                "task": tuner.assigned_task,
                "backend": tuner.capabilities.backend,
            }
            for key, tuner in self.tuners.items()
        }
