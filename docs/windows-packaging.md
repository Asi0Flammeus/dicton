# Windows Packaging

This project ships Windows builds as a user-friendly Inno Setup installer backed by a PyInstaller application bundle.

## Current Scope

The Windows bundle is intended for the fallback desktop workflow:

- `Alt+G` hotkey mode
- Basic transcription
- Translation to English
- Config UI via `dicton.exe --config`
- Experimental Windows context detection

Not in scope for the first Windows bundle:

- FN key support
- Linux-only playback mute control
- Full feature parity with Linux

## Build Locally on Windows

```powershell
python -m pip install -e ".[windows,context-windows,notifications,llm,configui,mistral,packaging]"
choco install innosetup -y
powershell -ExecutionPolicy Bypass -File scripts\build-windows.ps1
```

The output is:

- `dist\dicton\` - unpacked one-folder application bundle
- `dist\DictonSetup-<version>-x64.exe` - recommended installer for end users
- `dist\dicton-windows-portable-x64.zip` - portable archive for debugging/manual installs

## Bundle Layout

The packaged bundle includes:

- `dicton.exe` - windowless user-facing app
- `dicton-cli.exe` - console/debug entrypoint
- bundled package assets
- `.env.example`
- `README.md`

The one-folder bundle remains intentional internally because it is simpler to
debug and less fragile than a one-file executable. End users should receive the
installer, not the raw bundle.

## Installer Behavior

The installer:

- installs per-user to `%LOCALAPPDATA%\Programs\Dicton`
- creates Start Menu shortcuts
- optionally creates a Desktop shortcut
- optionally enables start-on-login via the HKCU Run registry key
- opens the setup wizard after install with `dicton.exe --config`
