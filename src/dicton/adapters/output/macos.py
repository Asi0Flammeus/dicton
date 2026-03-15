"""macOS text output via pynput (basic implementation)."""

from __future__ import annotations

import subprocess

from .base import TextOutput
from .fallback import PynputTextOutput


class MacOSTextOutput(TextOutput):
    """Text output via pynput for macOS — can be enhanced with pyobjc later."""

    def __init__(self):
        self._pynput_fallback = PynputTextOutput()

    def insert_text(self, text: str, delay_ms: int = 50) -> None:
        self._pynput_fallback.insert_text(text, delay_ms)

    def paste_text(self, text: str) -> bool:
        return self.replace_selection(text)

    def replace_selection(self, text: str) -> bool:
        try:
            process = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE, text=True)
            process.communicate(input=text, timeout=2.0)
            if process.returncode != 0:
                return False

            from pynput.keyboard import Key

            ctrl = self._pynput_fallback._get_keyboard_controller()
            ctrl.press(Key.cmd)
            ctrl.press("v")
            ctrl.release("v")
            ctrl.release(Key.cmd)
            return True

        except Exception:
            return False
