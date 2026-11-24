# Skybox Recon V2 — Windows GUI preview

This package adds a native Tkinter desktop shell around the supplied `skybox.py`
command-line engine. Launching `SkyboxRecon.exe` opens a persistent graphical
control centre rather than printing CLI usage and exiting.

## Build on GitHub Actions
Push this folder's contents to the `main` branch of `BajanBob/skybox`.
The workflow `.github/workflows/windows-gui.yml` builds a Windows x64
one-file GUI executable with PyInstaller and uploads `SkyboxRecon-Windows-GUI`
as a workflow artifact.

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
