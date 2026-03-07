# Windows Packaging

This project now includes a first Windows packaging path based on PyInstaller.

## Current Scope

The Windows bundle is intended for the fallback desktop workflow:

- `Alt+G` hotkey mode
- Basic transcription
- Translation to English
- Config UI via `dicton.exe --config-ui`
- Experimental Windows context detection

Not in scope for the first Windows bundle:

- FN key support
- Linux-only playback mute control
- Full feature parity with Linux

## Build Locally on Windows

```powershell
python -m pip install -e ".[windows,context-windows,notifications,llm,configui,mistral,packaging]"
powershell -ExecutionPolicy Bypass -File scripts\build-windows.ps1
```

The output is:

- `dist\dicton\` - unpacked one-folder application bundle
- `dist\dicton-windows-x64.zip` - distributable archive

## Bundle Layout

The packaged bundle includes:

- `dicton.exe`
- bundled package assets
- `.env.example`
- `README.md`

The one-folder bundle is intentional for the first Windows release path. It is
simpler to debug and less fragile than a one-file executable while the platform
support is still maturing.
