$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = Split-Path -Parent $ScriptDir
Set-Location $ProjectDir

function Get-DictonVersion {
    $InitPath = Join-Path $ProjectDir "src\dicton\__init__.py"
    $Match = Select-String -Path $InitPath -Pattern '^__version__ = "(?<version>[^"]+)"$' | Select-Object -First 1
    if (-not $Match) {
        throw "Could not read Dicton version from $InitPath"
    }
    return $Match.Matches[0].Groups["version"].Value
}

function Find-InnoSetupCompiler {
    $Command = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue
    if ($Command) {
        return $Command.Source
    }

    $Candidates = @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
    )

    foreach ($Candidate in $Candidates) {
        if ($Candidate -and (Test-Path $Candidate)) {
            return $Candidate
        }
    }

    throw "Inno Setup compiler not found. Install Inno Setup 6, or run: choco install innosetup -y"
}

$Version = Get-DictonVersion

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

$ArchivePath = Join-Path $ProjectDir "dist\dicton-windows-portable-x64.zip"
if (Test-Path $ArchivePath) {
    Remove-Item $ArchivePath -Force
}

Compress-Archive -Path (Join-Path $BundleDir "*") -DestinationPath $ArchivePath
Write-Host "==> Portable Windows bundle ready: $ArchivePath"

Write-Host "==> Building Dicton Windows installer"
$IsccPath = Find-InnoSetupCompiler
$InstallerPath = Join-Path $ProjectDir "dist\DictonSetup-$Version-x64.exe"
if (Test-Path $InstallerPath) {
    Remove-Item $InstallerPath -Force
}

& $IsccPath "/DAppVersion=$Version" "/O$ProjectDir\dist" "packaging\windows\dicton.iss"
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

if (-not (Test-Path $InstallerPath)) {
    throw "Expected installer not found: $InstallerPath"
}

Write-Host "==> Windows installer ready: $InstallerPath"
