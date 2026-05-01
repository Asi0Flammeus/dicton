"""Clipboard ABC for Dicton."""

from __future__ import annotations

from abc import ABC, abstractmethod


class Clipboard(ABC):
    """Read and write system clipboard contents."""

    @abstractmethod
    def get_clipboard(self) -> str | None:
        """Read text from system clipboard."""

    @abstractmethod
    def set_clipboard(self, text: str) -> bool:
        """Write text to system clipboard. Returns True on success."""


class NullClipboard(Clipboard):
    """No-op fallback when no clipboard mechanism is available."""

    def get_clipboard(self) -> str | None:
        return None

    def set_clipboard(self, text: str) -> bool:
        return False
