"""Text output ABC for Dicton."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod

from ...shared.config import config


class TextOutput(ABC):
    """Insert text into the active application."""

    @abstractmethod
    def insert_text(self, text: str, delay_ms: int = 50) -> None:
        """Insert text at cursor position."""

    @abstractmethod
    def paste_text(self, text: str) -> bool:
        """Paste text via clipboard. Returns True on success."""

    @abstractmethod
    def replace_selection(self, text: str) -> bool:
        """Replace current selection with text. Returns True on success."""

    def _verify_clipboard(self, expected_text: str, get_clipboard_fn) -> bool:
        """Poll until clipboard matches expected_text or max retries exceeded.

        X11 clipboard is asynchronous — xclip may exit before propagation.
        Comparison is whitespace-normalized.
        """
        verify_delay = config.CLIPBOARD_VERIFY_DELAY_MS / 1000.0
        max_retries = config.CLIPBOARD_MAX_RETRIES
        expected_stripped = expected_text.strip()

        for attempt in range(max_retries):
            time.sleep(verify_delay)
            current = get_clipboard_fn()
            if current is not None and current.strip() == expected_stripped:
                return True
            if config.DEBUG:
                print(f"⚠ Clipboard verify attempt {attempt + 1}/{max_retries}: mismatch")

        return False
