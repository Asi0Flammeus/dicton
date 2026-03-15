"""X11 selection reader via xclip."""

from __future__ import annotations

import subprocess

from .selection_base import SelectionReader


class X11SelectionReader(SelectionReader):
    """Selection/clipboard via xclip (X11 and XWayland)."""

    def get_selection(self) -> str | None:
        try:
            result = subprocess.run(
                ["xclip", "-selection", "primary", "-o"],
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
                print("xclip not installed. Install with: sudo apt install xclip")
            return None
        except (subprocess.TimeoutExpired, Exception):
            return None

    def get_clipboard(self) -> str | None:
        try:
            result = subprocess.run(
                ["xclip", "-selection", "clipboard", "-o"],
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
                ["xclip", "-selection", "clipboard"],
                stdin=subprocess.PIPE,
                text=True,
            )
            process.communicate(input=text, timeout=2.0)
            return process.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
            return False
