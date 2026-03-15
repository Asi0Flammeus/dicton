"""Selection/clipboard reader ABC for Dicton."""

from __future__ import annotations

from abc import ABC, abstractmethod


class SelectionReader(ABC):
    """Read selected text and clipboard contents."""

    @abstractmethod
    def get_selection(self) -> str | None:
        """Get currently selected/highlighted text."""

    def has_selection(self) -> bool:
        """Check if text is selected."""
        sel = self.get_selection()
        return sel is not None and len(sel) > 0

    @abstractmethod
    def get_clipboard(self) -> str | None:
        """Read text from system clipboard."""

    @abstractmethod
    def set_clipboard(self, text: str) -> bool:
        """Write text to system clipboard. Returns True on success."""


class NullSelectionReader(SelectionReader):
    """No-op fallback when no selection mechanism is available."""

    def get_selection(self) -> str | None:
        return None

    def get_clipboard(self) -> str | None:
        return None

    def set_clipboard(self, text: str) -> bool:
        return False
