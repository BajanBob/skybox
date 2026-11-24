import os
import time
import urllib.request

import pytest

from skybox_recon import dvb, spectrum
from skybox_recon.advisor import CognitiveAdvisor, RefTransponder, acquisition_plan, identify_satellite
from skybox_recon.streamer import TSStreamServer
from skybox_recon.testsignals import (DEMO_TRANSPONDERS, demo_rtl_power_csv, demo_sweep,
                                      demo_transport_stream)
from skybox_recon.ts_parser import TSParser, analyze_file, crc32_mpeg2


def test_crc32_mpeg2_vector():
    assert crc32_mpeg2(b"123456789") == 0x0376E6E7


def test_ts_parser_services_pids_codecs_and_satellite():
    p = TSParser()
    ts = demo_transport_stream()
    for i in range(0, len(ts), 777):       # arbitrary chunking must not matter
        p.feed(ts[i:i + 777])
    r = p.report()
    by_id = {s.service_id: s for s in r.services}
    assert set(by_id) == {101, 102}
    s1 = by_id[101]
    assert s1.service_name == "Test Card UHD" and s1.video_pids == (0x200,)
    assert s1.audio_pids == (0x201, 0x202) and not s1.scrambled
    codecs = {c.pid: (c.codec, c.language) for c in s1.components}
    assert codecs[0x200][0] == "H.265 / HEVC"
    assert codecs[0x201] == ("Dolby Digital Plus (E-AC-3)", "eng")
    assert codecs[0x203] == ("DVB subtitles", "eng")
    s2 = by_id[102]
    assert s2.service_name == "Météo HD" and s2.scrambled
    assert {c.codec for c in s2.components} == {"H.264 / AVC", "Dolby AC-4"}
    assert r.orbital_positions == ["28.2°E"]
    here = r.this_transponder
    assert here and here.frequency_khz == 11_778_000 and here.symbol_rate == 27_500_000
    assert here.modulation_system == "DVB-S2" and here.modulation == "8PSK" and here.polarization == "V"
    assert r.crc_errors == 0 and r.cc_errors == 0


def test_ts_parser_resyncs_after_garbage(tmp_path):
    path = tmp_path / "x.ts"
    path.write_bytes(b"\x00garbage\x12" + demo_transport_stream())
    r = analyze_file(str(path))
    assert r.sync_errors >= 1 and len(r.services) == 2


def test_blind_scan_accuracy():
    found = spectrum.detect_transponders(*demo_sweep(seed=11), lof_mhz=9750, pol="V")
    assert len(found) == len(DEMO_TRANSPONDERS)
    for t, (centre, sr, _lvl) in zip(found, DEMO_TRANSPONDERS):
        assert abs(t.if_mhz - centre) < 0.6
        assert abs(t.sr_ksym / 1000 - sr) <= 1.6
        assert t.rf_mhz == pytest.approx(centre + 9750, abs=0.6)
        assert t.pol == "V"


def test_sweep_csv_roundtrip():
    sweeps = spectrum.read_sweeps_csv(demo_rtl_power_csv(sweeps=3))
    assert len(sweeps) == 3
    freqs, levels = sweeps[0]
    assert freqs == sorted(freqs) and 949 < freqs[0] < 952 and len(freqs) == len(levels)
    assert len(spectrum.detect_transponders(freqs, levels)) == len(DEMO_TRANSPONDERS)


def test_sweep_commands():
    assert spectrum.sweep_command("rtl_power", once=True)[:3] == ["rtl_power", "-f", "950M:2150M:1000k"]
    assert spectrum.sweep_command("hackrf_sweep")[:3] == ["hackrf_sweep", "-f", "950:2150"]


def test_finder_tone_and_lock():
    f = spectrum.SatFinder(lock_db=10)
    weak = f.update(*demo_sweep(gain=0.15, seed=2))
    strong = f.update(*demo_sweep(gain=1.0, seed=3))
    assert strong.tone_hz > weak.tone_hz and strong.interval_ms < weak.interval_ms
    assert strong.locked and not weak.locked and f.peak >= strong.cn_db


def test_dvbv5_conf_and_lnb():
    conf = dvb.dvbv5_conf(dvb.TuneParams(freq_khz=10_847_000, sr=23_000_000, delsys="DVBS",
                                         mod="QPSK", fec="5/6", pol="V"))
    assert "MODULATION = QPSK" in conf and "POLARIZATION = VERTICAL" in conf and "ROLLOFF" not in conf
    assert dvb.lnb_for(11778) == (10600.0, True) and dvb.lnb_for(10847) == (9750.0, False)
    assert dvb.voltage_for("H") == 18 and dvb.voltage_for("V") == 13
    assert dvb.stream_id(3, 131070, "GOLD") == (1 << 26) | (131070 << 8) | 3
    with pytest.raises(ValueError):
        dvb.dvbv5_conf(dvb.TuneParams(freq_khz=1, sr=1, delsys="DVBS", mod="8PSK"))
    assert "256APSK" in dvb.MODULATIONS["DVBS2X"] and "pi/2-BPSK" in dvb.MODULATIONS["DVBS2X"]


def test_constellation_recovers_qpsk_and_8psk():
    np = pytest.importorskip("numpy")
    from skybox_recon.constellation import load_iq, recover
    from skybox_recon.testsignals import demo_iq
    r4 = recover(demo_iq(order=4, snr_db=20, freq_offset=0.003), 4e6, 1e6, order=4)
    assert r4.mer_db > 22 and abs(r4.freq_offset_hz - 12000) < 200
    r8 = recover(demo_iq(order=8, snr_db=22), 4e6, 1e6, order=8)
    assert r8.mer_db > 22
    noisy = recover(demo_iq(order=4, snr_db=8), 4e6, 1e6, order=4)
    assert noisy.mer_db < r4.mer_db


def test_load_iq_cu8(tmp_path):
    np = pytest.importorskip("numpy")
    from skybox_recon.constellation import load_iq
    path = tmp_path / "x.cu8"
    path.write_bytes(bytes([255, 0, 128, 128]))
    iq = load_iq(str(path))
    assert iq.size == 2 and iq[0].real > 0.99 and iq[0].imag < -0.99


def test_advisor_learns_and_identifies(tmp_path):
    adv = CognitiveAdvisor(str(tmp_path / "h.json"))
    weak = spectrum.detect_transponders(*demo_sweep(gain=0.5, seed=4))
    adv.record(weak, 9750, "H", -92)
    strong = spectrum.detect_transponders(*demo_sweep(gain=1.0, seed=5))
    adv.record(strong, 9750, "H", -92)
    tips = " ".join(str(t) for t in adv.advise(strong, -92, 9750, "H"))
    assert "Strongest carrier" in tips and "up" in tips
    assert "No carriers" in str(adv.advise([], -110, 9750, "H")[0])
    ref = [RefTransponder("TestSat", "28.2E", t.rf_mhz + 1, "H", t.sr_ksym) for t in strong[:5]]
    ref += [RefTransponder("OtherSat", "19.2E", 12000 + i * 40, "H", 27500) for i in range(5)]
    ranked = identify_satellite(strong, ref)
    assert ranked[0][0] == "TestSat" and ranked[0][3] == 5
    assert os.path.exists(tmp_path / "h.json")


def test_acquisition_plan_skips_missing_hardware():
    plan = acquisition_plan(have_sdr=True, have_dvb=False)
    assert plan[0].status == "pending" and plan[3].status == "skipped"


def test_lan_stream_server(tmp_path):
    ts = demo_transport_stream(10)
    src = tmp_path / "a.ts"
    src.write_bytes(ts)
    srv = TSStreamServer(str(src), port=0, bind="127.0.0.1")
    srv.start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{srv.port}/stream.ts", timeout=5) as resp:
            assert resp.headers["Content-Type"] == "video/mp2t"
            data = resp.read(len(ts) * 2)   # looping source keeps going
        assert data[:len(ts)] == ts and data[len(ts):2 * len(ts)] == ts
        p = TSParser()
        p.feed(data)
        assert len(p.report().services) == 2
    finally:
        srv.stop()
    assert srv.urls()[0].endswith(f":{srv.port}/stream.ts")


def test_band_plans_and_sdr_ranges():
    from skybox_recon.bands import BANDS, sweep_range
    nano = "RTL-SDR R820T2 / R828D (e.g. NESDR Nano 3, RTL-SDR Blog V3/V4)"
    lo, hi, warn = sweep_range(BANDS["S-band direct 2-4 GHz"], nano)
    assert "cannot reach" in warn
    assert sweep_range(BANDS["Wideband direct 1-6000 MHz"], "HackRF One")[:2] == (1, 6000)
    assert sweep_range(BANDS["C-band LNB (LO 5150)"], nano) == (950, 1450, "")
    assert dvb.if_to_rf(1575.42, 0) == 1575.42                     # direct: GNSS L1 stays put
    assert dvb.if_to_rf(1000, BANDS["Ka-band LNB (LO 18250)"].lof_mhz) == 19250
    assert dvb.if_to_rf(1000, 5150) == 4150                          # C-band inverts


def test_direct_l_band_narrow_carriers():
    # Simulated carriers remapped onto 1525-1559 MHz with 10 kHz bins: narrow carriers.
    f, l = demo_sweep(step_mhz=1200 / 3400, start_mhz=950, stop_mhz=2150, seed=3)
    f = [1525 + (x - 950) * 34 / 1200 for x in f]
    found = spectrum.detect_transponders(f, l, lof_mhz=0, min_sr_ksym=1)
    assert len(found) == len(DEMO_TRANSPONDERS)
    assert all(t.rf_mhz == t.if_mhz for t in found)
    assert 1525 < found[0].rf_mhz < 1559 and found[0].sr_ksym < 1500
