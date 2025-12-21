#!/bin/bash
# Quick run script for Dicton

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Virtual environment not found. Please run ./install.sh first"
    exit 1
fi

# Activate virtual environment and run
source venv/bin/activate
python src/main.py "$@"
