"""Earned core ports for external runtime boundaries."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class AudioSessionControl(Protocol):
    """Control system audio during a dictation session."""

    def start_recording(self) -> None:
        """Apply audio controls when recording starts."""

    def stop_recording(self) -> None:
        """Restore audio controls when recording stops."""

    def cancel_recording(self) -> None:
        """Restore audio controls when recording is cancelled."""


@runtime_checkable
class TextOutput(Protocol):
    """Insert text into the active application."""

    def insert_text(self, text: str, delay_ms: int = 50) -> None:
        """Insert text at cursor position."""

    def paste_text(self, text: str) -> bool:
        """Paste text via clipboard. Returns True on success."""


@runtime_checkable
class UIFeedback(Protocol):
    """User-visible notifications."""

    def notify(self, title: str, message: str) -> None:
        """Display a notification."""
