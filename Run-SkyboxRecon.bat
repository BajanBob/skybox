@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title SKYBOX RECON - command menu
if not exist "skybox-cli.exe" (
  echo skybox-cli.exe was not found in this folder.
  echo Download the Windows ZIP from GitHub Actions and keep all files together.
  pause
  exit /b 1
)

:MENU
cls
echo =====================================================
echo                 SKYBOX RECON
echo                  WINDOWS x64
echo =====================================================
echo.
echo  1. Run offline self-test
echo  2. List available COM ports
echo  3. UART console probe
echo 4. Firmware image analysis help
echo 5. Static analysis help
echo 6. IPL loader help  [FLASH WRITE DISABLED BY GUIDANCE]
echo  7. YMODEM transfer help
echo  8. USB upgrade image help
echo  9. DVB-S/S2/S2X tuning help
echo 10. Low-symbol-rate SDR help
echo 11. Transport-stream remux help
echo 12. Show all command help
echo  0. Exit
echo.
set "choice="
set /p "choice=Choose an option: "
if "%choice%"=="1" goto SELFTEST
if "%choice%"=="2" goto PORTS
if "%choice%"=="3" goto UART
if "%choice%"=="4" goto FW
if "%choice%"=="5" goto STATIC
if "%choice%"=="6" goto IPL
if "%choice%"=="7" goto YMODEM
if "%choice%"=="8" goto USB
if "%choice%"=="9" goto TUNE
if "%choice%"=="10" goto LOWSDR
if "%choice%"=="11" goto REMUX
if "%choice%"=="12" goto HELP
if "%choice%"=="0" exit /b 0
echo Invalid selection.
pause
goto MENU

:SELFTEST
"%~dp0skybox-cli.exe" selftest
goto DONE
:PORTS
echo Available serial (COM) ports:
powershell -NoProfile -Command "$p=[System.IO.Ports.SerialPort]::GetPortNames() | Sort-Object; if ($p) {$p} else {'No COM ports detected.'}"
goto DONE
:UART
call :PORTPROMPT
if not defined port goto MENU
"%~dp0skybox-cli.exe" uart "%port%" --parity E --dwell 1
goto DONE
:FW
echo Usage: skybox-cli.exe fw "firmware-image.bin" [--carve] [--extract output-folder]
"%~dp0skybox-cli.exe" fw --help
goto DONE
:STATIC
"%~dp0skybox-cli.exe" static --help
goto DONE
:IPL
echo WARNING: Do not use IPL flash-write on a physical receiver.
echo Known addressing and write-path defects must be corrected and validated first.
"%~dp0skybox-cli.exe" ipl --help
goto DONE
:YMODEM
"%~dp0skybox-cli.exe" ymodem --help
goto DONE
:USB
"%~dp0skybox-cli.exe" usb --help
goto DONE
:TUNE
"%~dp0skybox-cli.exe" tune --help
goto DONE
:LOWSDR
"%~dp0skybox-cli.exe" lowsdr --help
goto DONE
:REMUX
"%~dp0skybox-cli.exe" remux --help
goto DONE
:HELP
"%~dp0skybox-cli.exe" --help
goto DONE

:PORTPROMPT
set "port="
set /p "port=Enter COM port (example COM3): "
if not defined port exit /b 0
if /i not "%port:~0,3%"=="COM" (
  echo Please enter a Windows COM port such as COM3.
  set "port="
)
exit /b 0

:DONE
echo.
echo -----------------------------------------------------
echo Command finished. Review any output or error above.
echo -----------------------------------------------------
pause
goto MENU
