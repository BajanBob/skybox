SKYBOX RECON - WINDOWS x64

CONTENTS OF THE ZIP
- SkyboxRecon.exe            Desktop window (double-click this).
- skybox-cli.exe             Command-line engine for scripts and the menu.
- Launch-SkyboxRecon.bat     Starts SkyboxRecon.exe.
- Run-SkyboxRecon.bat        Text menu around skybox-cli.exe.
- Create-Desktop-Shortcut.ps1  Adds a "Skybox Recon" desktop shortcut.

GETTING THE BUILD
1. GitHub > BajanBob/skybox > Actions > "Skybox Recon - Windows Build".
2. Open the latest green run and download the SkyboxRecon-Windows-x64 artifact.
3. Extract the ZIP to a normal folder (not inside the ZIP viewer).
4. Double-click SkyboxRecon.exe. The first start takes a few seconds while
   the one-file program unpacks; then the window opens and stays open.

IF IT DOES NOT START
- Windows SmartScreen may show "Windows protected your PC" for unsigned
  programs: choose More info > Run anyway.
- Some antivirus products quarantine PyInstaller one-file programs. Restore
  the file / add an exclusion for the folder.
- Any start-up error is shown in a dialog and written to
  SkyboxRecon-error.log next to the exe (or in your user folder).

SAFETY
The GUI does not expose firmware flashing. Do not use IPL flash-write
against a physical receiver until the write path is independently
validated. The self-test is offline and needs no hardware.
