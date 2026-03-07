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

    if IS_WINDOWS or IS_MACOS:
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
    if not IS_LINUX:
        return {
            "supported": False,
            "ok": False,
            "message": "Autostart management is currently implemented for Linux only.",
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
