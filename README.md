# Skybox Recon 6.0 “Beryl”

This package adds a native Tkinter desktop shell around the supplied `skybox.py`
command-line engine. Launching `SkyboxRecon.exe` opens a persistent graphical
control centre rather than printing CLI usage and exiting.

## Downloads (v6.0.0 Beryl)
GitHub Actions (`.github/workflows/build.yml`) builds and tests every platform
on each push and pull request. Pushing a tag such as `v2.0.0` also publishes a
GitHub Release with all files attached.

| Platform | File | Notes |
|---|---|---|
| Windows x64 installer | `SkyboxRecon-6.0.0-Windows-x64-Setup.exe` | Desktop + Start-menu shortcuts, uninstaller; no admin needed |
| Windows x64 portable | `SkyboxRecon-6.0.0-Windows-x64-Portable.zip` | `SkyboxRecon.exe` (GUI) + `skybox-cli.exe` |
| Linux x86_64 | `SkyboxRecon-6.0.0-Linux-x86_64.zip` | GUI + CLI, `install.sh` adds menu/desktop launcher |
| Android | `SkyboxRecon-6.0.0-Android.apk` | Mobile edition: services/PIDs + satellite from .ts files, S2X tuning builder, firmware, frames, self-test |

The desktop `SkyboxRecon` executable bundles the `skybox.py` engine; run
`SkyboxRecon --cli <command>` to use it directly. The Android edition
(`mobile/`) is a Capacitor app with a JavaScript port of the offline engine
functions; it does not drive serial hardware.

To sign Android release builds with a stable key, add the repository secrets
`ANDROID_KEYSTORE_BASE64`, `ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_ALIAS` and
`ANDROID_KEY_PASSWORD`; otherwise CI produces a debug-signed APK.

Do not commit `dist/`, `build/` or `.spec` files; CI produces them.

## Local run (Python 3.10+)
```powershell
py -m pip install -r requirements.txt
py skybox_gui.py
```

## What Beryl does

| Feature | Desktop (Windows / Linux) | Android | Needs |
|---|---|---|---|
| Spectrum analyser + waterfall (950–2150 MHz IF, IF and RF scales) | ✓ | – | RTL-SDR (`rtl_power`) or HackRF (`hackrf_sweep`), LNB power inserter |
| Satellite finder with beep (pitch and rate rise with C/N, steady tone at lock, peak hold) | ✓ | – | as above |
| Blind scan: carrier detection, symbol-rate estimate from −3 dB width, duplicate filter | ✓ | – | as above |
| Constellation + MER/EVM (BPSK, QPSK, 8PSK) from IQ captures | ✓ | – | IQ file, or `rtl_sdr` / `hackrf_transfer` |
| Services/PIDs: PAT, PMT, SDT, NIT; video/audio/subtitle/PCR PIDs, codecs, languages, scrambling | ✓ | ✓ | a `.ts` recording |
| Satellite identification from the NIT orbital position, or by pattern against your transponder list | ✓ | NIT only | |
| DVB-S/S2/S2X tuning: all S2X modulations, LNB presets, 22 kHz, 13/18 V, DiSEqC, MIS/PLS, inversion | ✓ | builder | Linux DVB-S2 adapter + `dvbv5-zap` |
| Cognitive receiver: auto-acquire (sweep → detect → tune → record → identify) and advice from scan history | ✓ | – | SDR; DVB adapter for the tune/record steps |
| Dual tuner A/B on two DVB adapters | ✓ (Linux) | – | two adapters with separate RF inputs |
| Local-network AV streaming (`http://<pc>:8090/stream.ts`, Wi-Fi 6 or any LAN, no internet) | ✓ | – | |
| Firmware lab, UART probe, self-test | ✓ | firmware + self-test | |

Every simulated source (spectrum, IQ, transport stream) is labelled “SIMULATED” and
exists so each feature can be tried and tested without a dish.

Not included: audio/video decoding (use VLC/mpv on the stream), conditional-access
descrambling, and firmware flashing from the GUI. Real reception of each DVB-S2X
mode depends on the demodulator silicon and driver.

## Command line

```
skybox-cli scan --tool rtl_power --lof 9750 --pol H      # blind scan + advisor
skybox-cli finder --tool hackrf_sweep                    # finder with beep
skybox-cli pids capture.ts                               # services, PIDs, satellite
skybox-cli constel capture.cu8 --rate 2400000 --sr 500000 --mod QPSK
skybox-cli stream capture.ts --follow                    # LAN streaming
skybox-cli tune --freq 11778000 --sr 27500000 --delsys DVBS2X --mod 16APSK --pol V --print-only
skybox-cli selftest
```
