# Skybox Recon V2 — Windows GUI preview

This package adds a native Tkinter desktop shell around the supplied `skybox.py`
command-line engine. Launching `SkyboxRecon.exe` opens a persistent graphical
control centre rather than printing CLI usage and exiting.

## Build on GitHub Actions
Push this folder's contents to the `main` branch of `BajanBob/skybox`.
The workflow `.github/workflows/build-windows.yml` builds, tests and uploads
the `SkyboxRecon-Windows-x64` ZIP artifact containing:

- `SkyboxRecon.exe` — the desktop window (built from `skybox_gui.py`,
  windowed, with the `skybox.py` engine bundled inside; run
  `SkyboxRecon.exe --cli <command>` to use the engine directly).
- `skybox-cli.exe` — the console engine (built from `skybox.py`).

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
