"""Pynput-based fallback text output for Dicton (cross-platform)."""

from __future__ import annotations

import time

from .base import TextOutput


class PynputTextOutput(TextOutput):
    """Fallback text output using pynput character-by-character typing."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._keyboard_controller = None

    def _get_pynput_components(self):
        """Import pynput lazily so Linux startup can avoid X-only backends."""
        try:
            from pynput import keyboard as pynput_keyboard
            from pynput.keyboard import Controller as KeyboardController
            from pynput.keyboard import Key
        except Exception as exc:  # pragma: no cover - depends on local desktop backend
            raise ImportError(str(exc)) from exc

        return pynput_keyboard, KeyboardController, Key

    def _get_keyboard_controller(self):
        """Create the pynput controller only when needed."""
        if self._keyboard_controller is None:
            _, controller_cls, _ = self._get_pynput_components()
            self._keyboard_controller = controller_cls()
        return self._keyboard_controller

    def insert_text(self, text: str, delay_ms: int = 50) -> None:
        if not text:
            return
        try:
            delay_seconds = delay_ms / 1000.0
            ctrl = self._get_keyboard_controller()
            for char in text:
                ctrl.type(char)
                time.sleep(delay_seconds)
        except Exception as e:
            print(f"⚠ Text insertion error: {e}")

    def paste_text(self, text: str) -> bool:
        return False
