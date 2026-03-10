#!/usr/bin/env bash

echo
echo "POS for Charity"
echo

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_ROOT/backend"

# Check if installed
if [ ! -d "venv" ]; then
    echo "Run install.sh first to set up the application."
    exit 1
fi

# Activate venv
source venv/bin/activate

echo "Starting POS for Charity..."
echo
echo "Open in browser: http://localhost:8000"
echo "To access from other devices: http://YOUR_IP:8000"
echo
echo "Press Ctrl+C to stop the server."
echo

python main.py
