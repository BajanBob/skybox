# Skybox Recon V2 — Windows GUI preview

This package adds a native Tkinter desktop shell around the supplied `skybox.py`
command-line engine. Launching `SkyboxRecon.exe` opens a persistent graphical
control centre rather than printing CLI usage and exiting.

## Downloads (v2.0.0)
GitHub Actions (`.github/workflows/build.yml`) builds and tests every platform
on each push and pull request. Pushing a tag such as `v2.0.0` also publishes a
GitHub Release with all files attached.

| Platform | File | Notes |
|---|---|---|
| Windows x64 installer | `SkyboxRecon-2.0.0-Windows-x64-Setup.exe` | Desktop + Start-menu shortcuts, uninstaller; no admin needed |
| Windows x64 portable | `SkyboxRecon-2.0.0-Windows-x64-Portable.zip` | `SkyboxRecon.exe` (GUI) + `skybox-cli.exe` |
| Linux x86_64 | `SkyboxRecon-2.0.0-Linux-x86_64.zip` | GUI + CLI, `install.sh` adds menu/desktop launcher |
| Android | `SkyboxRecon-2.0.0-Android.apk` | Mobile edition: offline self-test, firmware analysis, tuning and frame tools |

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

## Current scope
Implemented in this GUI shell: overview, persistent diagnostics log, offline
self-test, firmware image analysis/carving, UART probe form, and DVB tuning
command builder. Firmware analysis is read-only.

Not implemented by this shell: live spectrum/waterfall acquisition, blind-scan
engine, live PID/service parser, audio/video decoding, dual independent tuner
hardware drivers, Wi-Fi AV transmitter, or firmware flashing. The interface
explicitly labels these limits. Never flash a receiver using unverified
procedures or firmware.
