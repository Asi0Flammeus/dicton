"""macOS selection reader via pbpaste/pbcopy."""

from __future__ import annotations

import subprocess

from .selection_base import SelectionReader


class MacOSSelectionReader(SelectionReader):
    """Selection/clipboard via pbpaste/pbcopy (macOS).

    macOS has no PRIMARY selection concept — get_selection() returns
    clipboard content (the closest equivalent).
    """

    def get_selection(self) -> str | None:
        return self.get_clipboard()

    def get_clipboard(self) -> str | None:
        try:
            result = subprocess.run(
                ["pbpaste"],
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
            process = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE, text=True)
            process.communicate(input=text, timeout=2.0)
            return process.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
            return False
