# Dicton - Windows PowerShell Installer
# Run as: powershell -ExecutionPolicy Bypass -File scripts\install.ps1

$ErrorActionPreference = "Stop"

Write-Host "========================================"
Write-Host "Dicton Windows Installer"
Write-Host "========================================"
Write-Host ""

# Change to script directory parent
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = Split-Path -Parent $ScriptDir
Set-Location $ProjectDir

# Check Python
try {
    $pythonVersion = python --version 2>&1
    Write-Host "Found: $pythonVersion"
} catch {
    Write-Host "ERROR: Python not found in PATH" -ForegroundColor Red
    Write-Host "Please install Python 3.10+ from https://python.org"
    exit 1
}

# Check Python version
$versionCheck = python -c "import sys; exit(0 if sys.version_info >= (3, 10) else 1)" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Python 3.10+ required" -ForegroundColor Red
    exit 1
}

# Create venv
Write-Host ""
Write-Host "[1/4] Creating virtual environment..." -ForegroundColor Cyan
if (Test-Path "venv") {
    Write-Host "Virtual environment already exists, skipping..."
} else {
    python -m venv venv
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: Failed to create virtual environment" -ForegroundColor Red
        exit 1
    }
}

# Activate venv
Write-Host "[2/4] Activating virtual environment..." -ForegroundColor Cyan
& .\venv\Scripts\Activate.ps1

# Upgrade pip
Write-Host "[3/4] Upgrading pip..." -ForegroundColor Cyan
python -m pip install --upgrade pip

# Install dependencies
Write-Host "[4/4] Installing dependencies..." -ForegroundColor Cyan
pip install -r requirements.txt

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "WARNING: Some dependencies may have failed to install." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "PyAudio installation on Windows:"
    Write-Host "  If PyAudio fails, try: pip install pipwin; pipwin install pyaudio"
    Write-Host "  Or download wheel from: https://www.lfd.uci.edu/~gohlke/pythonlibs/#pyaudio"
    Write-Host ""
}

Write-Host ""
Write-Host "========================================"
Write-Host "Installation complete!" -ForegroundColor Green
Write-Host "========================================"
Write-Host ""
Write-Host "Setup:"
Write-Host "  1. Copy .env.example to .env"
Write-Host "  2. Add your ELEVENLABS_API_KEY to .env"
Write-Host ""
Write-Host "Run:"
Write-Host "  .\run.bat"
Write-Host "  or: .\venv\Scripts\python.exe src\main.py"
Write-Host ""
