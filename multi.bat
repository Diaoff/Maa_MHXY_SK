@echo off
chcp 65001 >nul 2>&1
title Maa_MHXY_SK - 多开启动器

echo ========================================
echo   Maa_MHXY_SK 多开启动器
echo ========================================
echo.

cd /d "%~dp0"

echo [1/2] 检查 Python 环境...
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Python，请先安装 Python 3.8+
    pause
    exit /b 1
)
for /f "tokens=*" %%i in ('python --version 2^>^&1') do echo      %%i

echo [2/2] 启动多开...
echo.
python tools/run_multi_instance.py %*
if errorlevel 1 (
    echo.
    echo [错误] 多开启动失败
    pause
)
