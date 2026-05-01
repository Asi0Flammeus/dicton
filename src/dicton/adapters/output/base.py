"""Text output ABC for Dicton."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod


class TextOutput(ABC):
    """Insert text into the active application."""

    def __init__(
        self,
        *,
        debug: bool = False,
        clipboard_verify_delay_ms: int = 50,
        clipboard_max_retries: int = 5,
    ) -> None:
        self._debug = debug
        self._clipboard_verify_delay_ms = clipboard_verify_delay_ms
        self._clipboard_max_retries = clipboard_max_retries

    @abstractmethod
    def insert_text(self, text: str, delay_ms: int = 50) -> None:
        """Insert text at cursor position."""

    @abstractmethod
    def paste_text(self, text: str) -> bool:
        """Paste text via clipboard. Returns True on success."""

    def _verify_clipboard(self, expected_text: str, get_clipboard_fn) -> bool:
        """Poll until clipboard matches expected_text or max retries exceeded.

        X11 clipboard is asynchronous — xclip may exit before propagation.
        Comparison is whitespace-normalized.
        """
        verify_delay = self._clipboard_verify_delay_ms / 1000.0
        max_retries = self._clipboard_max_retries
        expected_stripped = expected_text.strip()

        for attempt in range(max_retries):
            time.sleep(verify_delay)
            current = get_clipboard_fn()
            if current is not None and current.strip() == expected_stripped:
                return True
            if self._debug:
                print(f"⚠ Clipboard verify attempt {attempt + 1}/{max_retries}: mismatch")

        return False
