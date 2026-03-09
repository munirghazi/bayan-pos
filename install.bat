@echo off
chcp 65001 >nul
title POS for Charity - Installation

echo.
echo ========================================
echo   POS for Charity - Installation
echo ========================================
echo.

:: Get script directory (project root)
set "PROJECT_ROOT=%~dp0"
set "PROJECT_ROOT=%PROJECT_ROOT:~0,-1%"
cd /d "%PROJECT_ROOT%"

:: Check Python
echo [1/4] Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH.
    echo Please install Python 3.10+ from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)
python --version

:: Python 3.13+ may lack pre-built wheels; requires Visual Studio Build Tools to compile
python -c "import sys; sys.exit(0 if sys.version_info < (3, 13) else 1)" 2>nul
if errorlevel 1 (
    echo.
    echo WARNING: Python 3.13+ detected. Some packages may need to be built from source.
    echo If installation fails, use Python 3.11 or 3.12 instead:
    echo   https://www.python.org/downloads/release/python-3119/
    echo   https://www.python.org/downloads/release/python-3120/
    echo.
    pause
)
echo.

:: Create virtual environment in backend
echo [2/4] Creating virtual environment...
cd backend
if exist venv (
    echo Virtual environment already exists.
) else (
    python -m venv venv
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo Virtual environment created.
)
echo.

:: Install Python dependencies
echo [3/4] Installing Python dependencies...
call venv\Scripts\activate.bat
pip install --upgrade pip -q
pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo ERROR: Failed to install dependencies.
    echo.
    echo If you see "pydantic-core" or "link.exe not found" errors:
    echo   - Python 3.13/3.14 may not have pre-built packages. Use Python 3.11 or 3.12.
    echo   - Download: https://www.python.org/downloads/release/python-3119/
    echo   - Then delete the "backend\venv" folder and run install.bat again.
    echo.
    pause
    exit /b 1
)
echo Dependencies installed successfully.
echo.

:: Check if frontend is built
echo [4/4] Checking frontend build...
cd ..
if exist "frontend\dist\index.html" (
    echo Frontend build found. Ready to run.
) else (
    echo WARNING: Frontend build not found.
    echo.
    where npm >nul 2>&1
    if errorlevel 1 (
        echo Node.js/npm is not installed. You need to either:
        echo   - Copy the frontend\dist folder from your development PC, OR
        echo   - Install Node.js and run: cd frontend ^&^& npm install ^&^& npm run build
    ) else (
        echo Building frontend...
        cd frontend
        call npm install
        call npm run build
        cd ..
        if exist "frontend\dist\index.html" (
            echo Frontend built successfully.
        ) else (
            echo WARNING: Frontend build may have failed. Check the output above.
        )
    )
)
echo.

echo ========================================
echo   Installation complete!
echo ========================================
echo.
echo To start the application, run: start.bat
echo Or double-click start.bat
echo.
pause
