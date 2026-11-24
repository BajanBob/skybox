from skybox_recon import devices as dv


def test_lookup_known_ids():
    assert dv.lookup("0BDA", "2838")[1].startswith("RTL-SDR")
    assert dv.lookup("1d50", "6089")[2] == "HackRF One"
    assert dv.lookup("303a", "1001")[0] == "serial"      # any ESP32 PID
    assert dv.lookup("dead", "beef") is None


def test_best_picks():
    devs = [dv.Device("serial", "ESP32", "303a", "1001", port="COM7"),
            dv.Device("serial", "CP210x", "10c4", "ea60", port="COM5"),
            dv.Device("sdr", "RTL-SDR (RTL2832U)", "0bda", "2838", sdr_key="k1"),
            dv.Device("sdr", "HackRF One", "1d50", "6089", sdr_key="HackRF One")]
    assert dv.best_serial(devs) == "COM5"           # real USB-UART preferred over ESP32
    assert dv.best_sdr(devs).name == "HackRF One"
    assert "COM5" in dv.summary(devs)


def test_detect_runs_anywhere():
    assert isinstance(dv.detect(probe_tuner=False), list)


def test_windows_parse_and_zadig_hint(monkeypatch):
    sample = ("USB\\VID_0BDA&PID_2838\\00000001|RTL2832UUSB\n"
              "USB\\VID_10C4&PID_EA60\\0001|silabser\n")
    monkeypatch.setattr(dv, "_run", lambda *a, **k: sample)
    monkeypatch.setattr(dv.sys, "platform", "win32")
    monkeypatch.setattr(dv, "scan_serial", lambda: [])
    found = dv.detect(probe_tuner=False)
    assert found[0].name.startswith("RTL-SDR") and "Zadig" in found[0].problem
    monkeypatch.setattr(dv, "_run", lambda *a, **k: "USB\\VID_0BDA&PID_2838\\1|WinUSB\n")
    assert dv.detect(probe_tuner=False)[0].problem == ""
