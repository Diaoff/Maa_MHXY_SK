@echo off
chcp 65001 >nul 2>&1
title Maa_MHXY_SK Launcher

echo ========================================
echo   Maa_MHXY_SK Launcher
echo ========================================
echo.

cd /d "%~dp0"

echo [1/2] Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.8+
    echo Download: https://www.python.org/downloads/
    pause
    exit /b 1
)
for /f "tokens=*" %%i in ('python --version 2^>^&1') do echo      %%i

echo.
echo [2/2] Launching MAA framework (MFAAvalonia)...
echo.

REM agent/main.py is spawned by the MAA framework, not run standalone.
REM The real one-click start is assets\MFAAvalonia.exe, which reads
REM assets\interface.json and launches ../agent/main.py via child_args.

set "MFAAVALONIA=assets\MFAAvalonia.exe"
if exist "%MFAAVALONIA%" (
    echo Found %MFAAVALONIA%, starting framework...
    echo Framework will load assets/interface.json and connect to the game window.
    echo.
    start "" "%MFAAVALONIA%"
    goto :eof
)

echo [ERROR] %MFAAVALONIA% not found.
echo.
echo Setup steps:
echo   1. Download MFAAvalonia for Windows from:
echo      https://github.com/SweetSmellFox/MFAAvalonia/releases
echo      (prefer a build with MaaFramework 5.11.x to match MaaFw==5.11.0)
echo   2. Extract all files into the assets\ folder of this project
echo      (so assets\MFAAvalonia.exe sits next to assets\interface.json)
echo   3. Make sure the game (Mhxy Sk) is running at 500x900 portrait
echo   4. Run this start.bat again
echo.
pause
