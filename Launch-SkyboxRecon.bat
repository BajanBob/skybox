@echo off
cd /d "%~dp0"
if not exist "SkyboxRecon.exe" (
  echo SkyboxRecon.exe was not found in this folder.
  pause
  exit /b 1
)
start "" "%~dp0SkyboxRecon.exe"
