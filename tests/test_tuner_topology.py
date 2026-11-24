import pytest
from skybox_recon.tuner_topology import (
    DualTunerCoordinator, PIDComponent, ServiceRecord, TunerCapabilities, TunerSession,
)


def make_tuner(name, independent=True):
    return TunerSession(name, TunerCapabilities("test-backend", independent))


def test_dual_tuner_requires_two_verified_independent_paths():
    coordinator = DualTunerCoordinator(make_tuner("A"), make_tuner("B"))
    coordinator.assign("A", "live-view")
    coordinator.assign("B", "blind-scan")
    assert coordinator.snapshot()["A"]["task"] == "live-view"
    assert coordinator.snapshot()["B"]["task"] == "blind-scan"
    with pytest.raises(ValueError):
        DualTunerCoordinator(make_tuner("A"), make_tuner("B", False))


def test_service_record_exposes_video_and_audio_pids():
    service = ServiceRecord(
        101, "Example", 20, 1, 100, 101,
        (PIDComponent(201, "video", "H.264"), PIDComponent(202, "audio", "AAC", "eng")),
    )
    assert service.video_pids == (201,)
    assert service.audio_pids == (202,)


def test_pid_range_is_checked():
    with pytest.raises(ValueError):
        PIDComponent(8192, "video")
