"""Windows backend: HKCU\\Run registry key."""

from __future__ import annotations

import shutil


def _windows_autostart_exec() -> str:
    """Prefer dictonw.exe (no console) for HKCU\\Run; fall back to dicton.exe."""
    return shutil.which("dictonw") or shutil.which("dicton") or "dictonw"


def enable() -> bool:
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


def disable() -> bool:
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
