@echo off
REM Push-to-Write - Windows launcher
cd /d "%~dp0"

REM Check if venv exists
if not exist "venv\Scripts\python.exe" (
    echo Virtual environment not found. Run install.bat first.
    pause
    exit /b 1
)

REM Activate venv and run
call venv\Scripts\activate.bat
python src\main.py
