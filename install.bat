@echo off
REM Dicton - Windows installer
echo ========================================
echo Dicton Windows Installer
echo ========================================
echo.

cd /d "%~dp0"

REM Check Python
where python >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found in PATH
    echo Please install Python 3.10+ from https://python.org
    pause
    exit /b 1
)

REM Check Python version
python -c "import sys; exit(0 if sys.version_info >= (3, 10) else 1)" 2>nul
if errorlevel 1 (
    echo ERROR: Python 3.10+ required
    python --version
    pause
    exit /b 1
)

echo [1/4] Creating virtual environment...
if exist venv (
    echo Virtual environment already exists, skipping...
) else (
    python -m venv venv
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment
        pause
        exit /b 1
    )
)

echo [2/4] Activating virtual environment...
call venv\Scripts\activate.bat

echo [3/4] Upgrading pip...
python -m pip install --upgrade pip

echo [4/4] Installing dependencies...
pip install -e ".[windows,context-windows,notifications,llm,configui,mistral]"
if errorlevel 1 (
    echo.
    echo WARNING: Some dependencies may have failed to install.
    echo.
    echo PyAudio installation on Windows:
    echo   If PyAudio fails, try: pip install pipwin ^&^& pipwin install pyaudio
    echo   Or download wheel from: https://www.lfd.uci.edu/~gohlke/pythonlibs/#pyaudio
    echo.
)

if not exist ".env" (
    copy /Y ".env.example" ".env" >nul
)

echo.
echo ========================================
echo Installation complete!
echo ========================================
echo.
echo Setup:
echo   1. Edit .env and add one STT API key
echo   2. Optional: add GEMINI_API_KEY or ANTHROPIC_API_KEY for translation
echo.
echo Run:
echo   run.bat
echo   or: venv\Scripts\python.exe -m dicton
echo.
pause
