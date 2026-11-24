@echo off
cd /d "%~dp0"
if exist "skybox-cli.exe" (skybox-cli.exe selftest) else (py -3 skybox.py selftest)
pause
