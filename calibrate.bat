@echo off
chcp 65001 >nul 2>&1
title Maa_MHXY_SK - 动态标定工具

echo ========================================
echo   Maa_MHXY_SK 动态标定工具
echo ========================================
echo.

cd /d "%~dp0"

echo [1/2] 检查 Python 环境...
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Python，请先安装 Python3.8+
    echo 下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)
for /f "tokens=*" %%i in ('python --version 2^>^&1') do echo      %%i

echo [2/2] 启动动态标定工具...
echo.
python tools/calibrate.py %*
if errorlevel 1 (
    echo.
    echo [错误] 标定工具启动失败
    pause
)
