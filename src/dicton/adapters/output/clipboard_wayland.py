"""Wayland clipboard via wl-paste/wl-copy."""

from __future__ import annotations

import subprocess

from .clipboard_base import Clipboard


class WaylandClipboard(Clipboard):
    """Clipboard via wl-paste/wl-copy (native Wayland)."""

    def __init__(self, *, debug: bool = False) -> None:
        self._debug = debug

    def get_clipboard(self) -> str | None:
        try:
            result = subprocess.run(
                ["wl-paste", "-n"],
                capture_output=True,
                text=True,
                timeout=2.0,
            )
            if result.returncode == 0 and result.stdout:
                return result.stdout.strip()
            return None
        except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
            return None

    def set_clipboard(self, text: str) -> bool:
        if not text:
            return False
        try:
            process = subprocess.Popen(
                ["wl-copy"],
                stdin=subprocess.PIPE,
                text=True,
            )
            process.communicate(input=text, timeout=2.0)
            return process.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
            return False
