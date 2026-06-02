@echo off
chcp 65001 >nul
title bw-auto 会员购抢票

echo.
echo   ╔══════════════════════════════╗
echo   ║   bw-auto — B站会员购抢票   ║
echo   ╚══════════════════════════════╝
echo.
echo   正在检查环境...

:: 检查 Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo   [错误] 未找到 Python，请先安装 Python 3.11+
    echo   下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)

:: 安装依赖（首次运行）
echo   正在安装依赖...
pip install -e . >nul 2>&1

:: 启动
echo   正在启动...
echo.
bw-auto web

pause
