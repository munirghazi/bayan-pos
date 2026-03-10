#!/usr/bin/env bash

echo
echo "========================================"
echo " POS for Charity - Installation"
echo "========================================"
echo

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_ROOT"

echo "[1/4] Checking Python..."
if ! command -v python3 &> /dev/null
then
    echo "ERROR: Python3 is not installed."
    echo "Install with:"
    echo "  Ubuntu/Debian: sudo apt install python3 python3-venv python3-pip"
    echo "  Fedora: sudo dnf install python3"
    exit 1
fi

python3 --version
echo

echo "[2/4] Creating virtual environment..."
cd backend

if [ -d "venv" ]; then
    echo "Virtual environment already exists."
else
    python3 -m venv venv
    echo "Virtual environment created."
fi

echo

echo "[3/4] Installing Python dependencies..."
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

if [ $? -ne 0 ]; then
    echo "ERROR: Failed to install dependencies."
    exit 1
fi

echo "Dependencies installed successfully."
echo

echo "[4/4] Checking frontend build..."
cd ..

if [ -f "frontend/dist/index.html" ]; then
    echo "Frontend build found. Ready to run."
else
    echo "Frontend build not found."

    if ! command -v npm &> /dev/null
    then
        echo "Node.js/npm not installed."
        echo "Install Node.js then run:"
        echo "cd frontend && npm install && npm run build"
    else
        echo "Building frontend..."
        cd frontend
        npm install
        npm run build
        cd ..
    fi
fi

echo
echo "========================================"
echo " Installation complete!"
echo "========================================"
echo
echo "To start the application run:"
echo "bash start.sh"
