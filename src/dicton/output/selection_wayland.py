"""Wayland selection reader via wl-paste/wl-copy."""

from __future__ import annotations

import subprocess

from .selection_base import SelectionReader


class WaylandSelectionReader(SelectionReader):
    """Selection/clipboard via wl-paste/wl-copy (native Wayland)."""

    def get_selection(self) -> str | None:
        try:
            result = subprocess.run(
                ["wl-paste", "-p", "-n"],
                capture_output=True,
                text=True,
                timeout=2.0,
            )
            if result.returncode == 0 and result.stdout:
                return result.stdout.strip()
            return None
        except FileNotFoundError:
            from ..config import config

            if config.DEBUG:
                print("wl-paste not found. Install with: sudo apt install wl-clipboard")
            return None
        except (subprocess.TimeoutExpired, Exception):
            return None

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
