# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules


spec_dir = Path(globals().get("SPECPATH", Path.cwd())).resolve()
project_root = spec_dir.parents[1]
datas = collect_data_files(
    "dicton",
    includes=[
        "assets/setup_ui.html",
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
    "backports",
    "backports.tarfile",
    "dicton.config_server",
    "dicton.context_detector_wayland",
    "dicton.context_detector_x11",
    "dicton.log_setup",
    "dicton.main",
    "dicton.stt_elevenlabs",
    "dicton.stt_mistral",
    "dicton.tray",
]
hiddenimports += collect_submodules("pynput")
hiddenimports += collect_submodules("Xlib")

# Collect GTK/gi typelibs for the system tray.
# PyGObject (gi) is a system apt package in /usr/lib/python3/dist-packages/,
# not installable via pip.  We must add it to pathex so PyInstaller can find it.
import subprocess
import sys

binaries = []
_system_sp = None
try:
    _system_sp = subprocess.check_output(
        [sys.executable, "-c",
         "import sysconfig; print(sysconfig.get_path('platlib', 'posix_prefix'))"],
        text=True,
    ).strip()
except Exception:
    _system_sp = "/usr/lib/python3/dist-packages"

_extra_paths = [p for p in [_system_sp, "/usr/lib/python3/dist-packages"] if Path(p).is_dir()]

# Temporarily add system paths so GiModuleInfo can introspect
for p in _extra_paths:
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    from PyInstaller.utils.hooks.gi import GiModuleInfo

    for gi_module, gi_version in [
        ("Gtk", "3.0"),
        ("Gdk", "3.0"),
        ("GdkPixbuf", "2.0"),
        ("AyatanaAppIndicator3", "0.1"),
    ]:
        info = GiModuleInfo(gi_module, gi_version)
        if info.available:
            gi_binaries, gi_datas, gi_imports = info.collect_typelib_data()
            binaries += gi_binaries
            datas += gi_datas
            hiddenimports += gi_imports
except Exception:
    pass  # gi not available at build time — tray will degrade gracefully

# Also collect the gi package itself and cairo bindings
try:
    hiddenimports += collect_submodules("gi")
    hiddenimports += collect_submodules("cairo")
except Exception:
    pass


a = Analysis(
    [str(project_root / "packaging" / "windows" / "pyinstaller_entry.py")],
    pathex=[str(project_root / "src")] + _extra_paths,
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pkg_resources"],
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
