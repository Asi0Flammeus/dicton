"""Windows selection reader via pyperclip."""

from __future__ import annotations

from .selection_base import SelectionReader


class WindowsSelectionReader(SelectionReader):
    """Selection/clipboard via pyperclip (Windows).

    Windows has no PRIMARY selection concept — get_selection() returns
    clipboard content (the closest equivalent).
    """

    def get_selection(self) -> str | None:
        return self.get_clipboard()

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
