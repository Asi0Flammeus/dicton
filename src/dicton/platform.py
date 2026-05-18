"""Cross-platform autostart toggle.

Linux: systemd --user unit. macOS: ~/Library/LaunchAgents plist. Windows:
HKCU Run registry key. Wizard calls `enable_autostart()`; the user can
disable from the same wizard later.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

SYSTEMD_UNIT = """[Unit]
Description=dicton voice dictation

[Service]
Type=simple
ExecStart={exec_path} --foreground
Restart=on-failure
RestartSec=2

[Install]
WantedBy=default.target
"""

LAUNCHD_PLIST = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
 "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>cat.dicton</string>
  <key>ProgramArguments</key>
  <array><string>{exec_path}</string></array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
</dict>
</plist>
"""


def _exec_path() -> str:
    found = shutil.which("dicton")
    return found or "dicton"


def _windows_autostart_exec() -> str:
    """Prefer dictonw.exe (no console) for HKCU\\Run; fall back to dicton.exe."""
    return shutil.which("dictonw") or shutil.which("dicton") or "dictonw"


def enable_autostart() -> bool:
    if sys.platform == "linux":
        return _enable_systemd()
    if sys.platform == "darwin":
        return _enable_launchd()
    if sys.platform == "win32":
        return _enable_windows()
    return False


def disable_autostart() -> bool:
    if sys.platform == "linux":
        return _disable_systemd()
    if sys.platform == "darwin":
        return _disable_launchd()
    if sys.platform == "win32":
        return _disable_windows()
    return False


def _enable_systemd() -> bool:
    unit_dir = Path.home() / ".config" / "systemd" / "user"
    unit_dir.mkdir(parents=True, exist_ok=True)
    unit_path = unit_dir / "dicton.service"
    unit_path.write_text(SYSTEMD_UNIT.format(exec_path=_exec_path()), encoding="utf-8")
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
    subprocess.run(["systemctl", "--user", "enable", "--now", "dicton.service"], check=False)
    return True


def _disable_systemd() -> bool:
    subprocess.run(["systemctl", "--user", "disable", "--now", "dicton.service"], check=False)
    unit_path = Path.home() / ".config" / "systemd" / "user" / "dicton.service"
    unit_path.unlink(missing_ok=True)
    return True


def _enable_launchd() -> bool:
    plist_dir = Path.home() / "Library" / "LaunchAgents"
    plist_dir.mkdir(parents=True, exist_ok=True)
    plist_path = plist_dir / "cat.dicton.plist"
    plist_path.write_text(LAUNCHD_PLIST.format(exec_path=_exec_path()), encoding="utf-8")
    subprocess.run(["launchctl", "unload", str(plist_path)], check=False)
    subprocess.run(["launchctl", "load", str(plist_path)], check=False)
    return True


def _disable_launchd() -> bool:
    plist_path = Path.home() / "Library" / "LaunchAgents" / "cat.dicton.plist"
    if plist_path.exists():
        subprocess.run(["launchctl", "unload", str(plist_path)], check=False)
        plist_path.unlink(missing_ok=True)
    return True


def _enable_windows() -> bool:
    try:
        import winreg
    except ImportError:
        return False
    key = winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Run",
        0,
        winreg.KEY_SET_VALUE,
    )
    try:
        winreg.SetValueEx(key, "dicton", 0, winreg.REG_SZ, _windows_autostart_exec())
    finally:
        winreg.CloseKey(key)
    return True


def _disable_windows() -> bool:
    try:
        import winreg
    except ImportError:
        return False
    key = winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Run",
        0,
        winreg.KEY_SET_VALUE,
    )
    try:
        winreg.DeleteValue(key, "dicton")
    except FileNotFoundError:
        pass
    finally:
        winreg.CloseKey(key)
    return True
