$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = Split-Path -Parent $ScriptDir
Set-Location $ProjectDir

Write-Host "==> Building Dicton Windows bundle"
python -m PyInstaller --noconfirm --clean packaging/windows/dicton.spec

if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

$BundleDir = Join-Path $ProjectDir "dist\dicton"
if (-not (Test-Path $BundleDir)) {
    throw "Expected bundle directory not found: $BundleDir"
}

Copy-Item ".env.example" (Join-Path $BundleDir ".env.example") -Force
Copy-Item "README.md" (Join-Path $BundleDir "README.md") -Force

$ArchivePath = Join-Path $ProjectDir "dist\dicton-windows-x64.zip"
if (Test-Path $ArchivePath) {
    Remove-Item $ArchivePath -Force
}

Compress-Archive -Path (Join-Path $BundleDir "*") -DestinationPath $ArchivePath
Write-Host "==> Windows bundle ready: $ArchivePath"
