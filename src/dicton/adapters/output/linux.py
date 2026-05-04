"""Linux text output via xdotool + xclip (X11/XWayland)."""

from __future__ import annotations

import subprocess

from .base import TextOutput
from .fallback import PynputTextOutput


class LinuxTextOutput(TextOutput):
    """Text output via xdotool + xclip for Linux (X11/XWayland)."""

    def __init__(
        self,
        clipboard=None,
        *,
        paste_threshold_words: int = -1,
        debug: bool = False,
        clipboard_verify_delay_ms: int = 50,
        clipboard_max_retries: int = 5,
    ):
        super().__init__(
            debug=debug,
            clipboard_verify_delay_ms=clipboard_verify_delay_ms,
            clipboard_max_retries=clipboard_max_retries,
        )
        self._clipboard = clipboard
        self._paste_threshold_words = paste_threshold_words
        self._pynput_fallback = PynputTextOutput()

    def insert_text(self, text: str, delay_ms: int = 50) -> None:
        if not text:
            return

        word_count = len(text.split())
        threshold = self._paste_threshold_words
        use_paste = threshold == -1 or (threshold > 0 and word_count > threshold)

        if use_paste:
            if self._debug:
                print(f"📋 Using paste for {word_count} words (threshold: {threshold})")
            if self.paste_text(text):
                return
            if self._debug:
                print("⚠ Paste failed, falling back to streaming")

        try:
            subprocess.run(
                ["xdotool", "type", "--delay", str(delay_ms), "--", text],
                timeout=60,
            )
        except FileNotFoundError:
            print("⚠ xdotool not found, using fallback method")
            self._pynput_fallback.insert_text(text, delay_ms)
        except Exception as e:
            print(f"⚠ xdotool error: {e}, using fallback")
            self._pynput_fallback.insert_text(text, delay_ms)

    def paste_text(self, text: str) -> bool:
        if self._clipboard is None:
            return False
        try:
            if not self._clipboard.set_clipboard(text):
                print("⚠ Failed to set clipboard, falling back to streaming")
                return False

            if not self._verify_clipboard(text, self._clipboard.get_clipboard):
                print("⚠ Clipboard verification failed, falling back to streaming")
                return False

            subprocess.run(
                ["xdotool", "key", "--clearmodifiers", "ctrl+shift+v"],
                timeout=10,
                check=False,
            )
            return True

        except FileNotFoundError:
            print("⚠ xdotool not found for paste operation")
            return False
        except Exception as e:
            print(f"⚠ Paste error: {e}, falling back to streaming")
            return False
