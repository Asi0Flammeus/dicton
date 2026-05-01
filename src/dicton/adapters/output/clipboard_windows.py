"""Windows clipboard via pyperclip."""

from __future__ import annotations

from .clipboard_base import Clipboard


class WindowsClipboard(Clipboard):
    """Clipboard via pyperclip (Windows)."""

    def get_clipboard(self) -> str | None:
        try:
            import pyperclip

            text = pyperclip.paste()
            return text if text else None
        except Exception:
            return None

    def set_clipboard(self, text: str) -> bool:
        try:
            import pyperclip

            pyperclip.copy(text)
            return True
        except Exception:
            return False
