# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules


spec_dir = Path(globals().get("SPECPATH", Path.cwd())).resolve()
project_root = spec_dir.parents[1]
datas = collect_data_files(
    "dicton",
    includes=[
        "assets/config_ui.html",
        "assets/logo.png",
        "default_contexts.json",
    ],
)
datas += [
    (str(project_root / ".env.example"), "."),
    (str(project_root / "README.md"), "."),
]

hiddenimports = [
    "dicton.config_server",
    "dicton.context_detector_wayland",
    "dicton.context_detector_x11",
    "dicton.main",
    "dicton.stt_elevenlabs",
    "dicton.stt_mistral",
]
hiddenimports += collect_submodules("pynput")
hiddenimports += collect_submodules("Xlib")


a = Analysis(
    [str(project_root / "packaging" / "windows" / "pyinstaller_entry.py")],
    pathex=[str(project_root / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="dicton",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="dicton",
)
