SKYBOX RECON - LINUX x86_64

CONTENTS
- SkyboxRecon          Desktop window (Tk). Run: ./SkyboxRecon
- skybox-cli           Command-line engine. Run: ./skybox-cli --help
- install.sh           Per-user install: menu entry, desktop launcher, ~/.local/bin
- skybox-recon.desktop / skybox-recon.png   launcher and icon

QUICK START
  unzip SkyboxRecon-*-Linux-x86_64.zip && cd SkyboxRecon-Linux-x86_64
  ./install.sh          (optional)
  ./SkyboxRecon

Built on Ubuntu 22.04 (glibc 2.35); runs on most current x86_64
distributions with an X11 or XWayland desktop.
Serial access needs membership of the dialout/uucp group.
`skybox-cli tune` uses dvbv5-zap (dvb-tools / v4l-utils); `lowsdr` uses
leandvb and SDR tools; `remux` uses ffmpeg. Install them separately.

SDR AND DVB TOOLS
  Debian/Ubuntu: sudo apt install rtl-sdr hackrf dvb-tools ffmpeg
  RTL-SDR or HackRF: spectrum, finder beep, blind scan, constellation.
  DVB-S2 adapter + dvbv5-zap: tuning, auto-acquire recording, dual tuner.
  Feed the SDR through an LNB power inserter with a DC block.

SAFETY
Firmware flashing is not exposed in the GUI. Do not use IPL flash-write on
a physical receiver until the write path is independently validated.
