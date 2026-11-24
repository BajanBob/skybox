SKYBOX RECON - WINDOWS x64 UPDATE PACKAGE

CONTENTS
- skybox.py: supplied Skybox Recon single-file source (unchanged)
- Run-SkyboxRecon.bat: menu launcher; keeps output visible
- requirements.txt: pyserial for serial hardware commands
- .github/workflows/build-windows.yml: Windows x64 GitHub Actions build

BUILD / RELEASE
1. Copy the contents into the root of https://github.com/BajanBob/skybox.
2. Ensure the default branch is main (or change the workflow branch filter).
3. Commit the workflow under .github/workflows/build-windows.yml.
4. In GitHub, open Actions > Skybox Recon - Windows Build > Run workflow.
5. Download the SkyboxRecon-Windows-x64 ZIP artifact after a successful run.
6. Extract the ZIP and double-click Run-SkyboxRecon.bat.

The workflow packages SkyboxRecon.exe, Run-SkyboxRecon.bat, and this readme
into one downloadable ZIP artifact.

SAFETY
The launcher intentionally provides IPL help but does not offer a one-click
flash-write action. The previously reviewed source has unresolved IPL write
and addressing concerns. Do not use IPL flash-write against a physical
receiver until those defects are corrected and independently validated.

HARDWARE COMMANDS
The program is a command-line toolkit, not yet a native graphical application.
The menu invokes selftest, lists COM ports, starts UART probing, and displays
command-specific help for operations that require additional arguments.
Hardware operations require compatible hardware, correct wiring, and suitable
external utilities/drivers. The self-test is offline and does not need a radio.
