"""Startup and autostart helpers for Dicton."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from .platform_utils import IS_LINUX, IS_MACOS, IS_WINDOWS

APP_NAME = "Dicton"
_WINDOWS_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def get_launch_command() -> list[str]:
    """Return the best command to launch Dicton from the current install."""
    if getattr(sys, "frozen", False):
        return [sys.executable]

    dicton_bin = shutil.which("dicton")
    if dicton_bin:
        return [dicton_bin]

    return [sys.executable, "-m", "dicton"]


def get_launch_command_string() -> str:
    """Return a shell-safe launch command."""
    if IS_WINDOWS:
        return " ".join(_quote_windows_arg(arg) for arg in get_launch_command())
    return shlex.join(get_launch_command())


def launch_background() -> dict[str, str | bool]:
    """Launch Dicton detached from the setup process."""
    cmd = get_launch_command()

    try:
        kwargs = {
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "start_new_session": True,
        }
        if IS_WINDOWS:
            kwargs["creationflags"] = (
                subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
            )

        subprocess.Popen(cmd, **kwargs)
        return {"supported": True, "ok": True, "message": f"Started {APP_NAME}."}
    except Exception as exc:
        return {"supported": True, "ok": False, "message": f"Failed to start {APP_NAME}: {exc}"}


def get_autostart_state() -> dict[str, str | bool]:
    """Report autostart support and current state."""
    if IS_LINUX:
        autostart_file = get_linux_autostart_file()
        return {
            "supported": True,
            "enabled": autostart_file.exists(),
            "path": str(autostart_file),
            "mode": "xdg-autostart",
        }

    if IS_WINDOWS:
        value = _read_windows_run_value()
        expected = get_launch_command_string()
        return {
            "supported": True,
            "enabled": value == expected,
            "path": _WINDOWS_RUN_KEY,
            "mode": "registry-run-key",
        }

    if IS_MACOS:
        return {
            "supported": False,
            "enabled": False,
            "path": "",
            "mode": "unavailable",
        }

    return {
        "supported": False,
        "enabled": False,
        "path": "",
        "mode": "unknown",
    }


def set_autostart(enabled: bool) -> dict[str, str | bool]:
    """Enable or disable autostart for the current user."""
    if IS_WINDOWS:
        return _set_windows_autostart(enabled)

    if not IS_LINUX:
        return {
            "supported": False,
            "ok": False,
            "message": "Autostart management is not implemented for this platform yet.",
        }

    autostart_file = get_linux_autostart_file()
    if enabled:
        autostart_file.parent.mkdir(parents=True, exist_ok=True)
        autostart_file.write_text(_render_linux_desktop_file(), encoding="utf-8")
        return {
            "supported": True,
            "ok": True,
            "message": "Dicton will start automatically when you log in.",
            "path": str(autostart_file),
        }

    autostart_file.unlink(missing_ok=True)
    return {
        "supported": True,
        "ok": True,
        "message": "Autostart disabled.",
        "path": str(autostart_file),
    }


def _quote_windows_arg(arg: str) -> str:
    """Quote one Windows command-line argument for registry/shortcut use."""
    return f'"{arg.replace(chr(34), chr(92) + chr(34))}"'


def _read_windows_run_value() -> str | None:
    """Return Dicton's HKCU Run value, if present."""
    if not IS_WINDOWS:
        return None

    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _WINDOWS_RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, APP_NAME)
            return str(value)
    except FileNotFoundError:
        return None
    except OSError:
        return None


def _set_windows_autostart(enabled: bool) -> dict[str, str | bool]:
    """Enable or disable per-user Windows autostart via the HKCU Run key."""
    try:
        import winreg

        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _WINDOWS_RUN_KEY) as key:
            if enabled:
                value = get_launch_command_string()
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, value)
                return {
                    "supported": True,
                    "ok": True,
                    "message": "Dicton will start automatically when you sign in.",
                    "path": _WINDOWS_RUN_KEY,
                }

            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass
            return {
                "supported": True,
                "ok": True,
                "message": "Autostart disabled.",
                "path": _WINDOWS_RUN_KEY,
            }
    except OSError as exc:
        return {
            "supported": True,
            "ok": False,
            "message": f"Failed to update Windows autostart: {exc}",
            "path": _WINDOWS_RUN_KEY,
        }


def get_linux_autostart_file() -> Path:
    """Return the XDG autostart desktop entry path."""
    return Path.home() / ".config" / "autostart" / "dicton.desktop"


def _render_linux_desktop_file() -> str:
    launch_command = get_launch_command_string()
    icon_path = ""
    if getattr(sys, "frozen", False):
        icon_candidate = Path(sys.executable).resolve().parent / "logo.png"
        if icon_candidate.exists():
            icon_path = f"Icon={icon_candidate}\n"

    desktop_entry = f"""[Desktop Entry]
Type=Application
Name={APP_NAME}
Comment=Voice dictation app
Exec={launch_command}
Terminal=false
Categories=Utility;
X-GNOME-Autostart-enabled=true
StartupNotify=false
{icon_path}"""
    return desktop_entry


def has_display_session() -> bool:
    """Return whether a desktop session is available for launching the app."""
    if IS_LINUX:
        return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    return True
