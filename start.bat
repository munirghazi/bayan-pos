@echo off
chcp 65001 >nul
title POS for Charity

set "PROJECT_ROOT=%~dp0"
set "PROJECT_ROOT=%PROJECT_ROOT:~0,-1%"
cd /d "%PROJECT_ROOT%\backend"

:: Check if installed
if not exist "venv" (
    echo Run install.bat first to set up the application.
    pause
    exit /b 1
)

:: Activate venv and run
call venv\Scripts\activate.bat

echo Starting POS for Charity...
echo.
echo Open in browser: http://localhost:8000
echo To access from other devices: http://YOUR_IP:8000
echo.
echo Press Ctrl+C to stop the server.
echo.

python main.py

pause
