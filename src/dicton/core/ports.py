"""Core ports (interfaces) for Dicton.

These protocols define the boundaries between the core orchestration
and platform/vendor-specific adapters. They are intentionally small and
capability-oriented to keep the core decoupled.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol


class AudioCapture(Protocol):
    """Capture audio for a recording session."""

    def record(self):
        """Record audio until stopped; returns audio buffer or None."""

    def stop(self) -> None:
        """Stop recording and proceed to processing."""

    def cancel(self) -> None:
        """Cancel recording and discard audio."""


class STTService(Protocol):
    """Speech-to-text transcription service."""

    def transcribe(self, audio) -> str | None:
        """Transcribe audio and return text."""


class TextProcessor(Protocol):
    """Post-processing for transcribed text."""

    def process(self, text: str, mode, selected_text=None, context=None) -> str | None:
        """Process text based on mode/context."""


class ContextProvider(Protocol):
    """Provides context about the active app/window."""

    def get_context(self):
        """Return a context object or None."""


class TextOutput(Protocol):
    """Outputs text to the active application."""

    def output(self, text: str, mode, replace_selection: bool, context=None) -> None:
        """Emit text to the active app."""


class UIFeedback(Protocol):
    """User-visible notifications."""

    def notify(self, title: str, message: str) -> None:
        """Display a notification."""


class MetricsSink(Protocol):
    """Latency/metrics tracking."""

    def start_session(self) -> None:
        """Start a metrics session."""

    def measure(self, name: str, **kwargs):
        """Return a context manager for timing a block."""

    def end_session(self):
        """End the session and return a summary."""


# Convenience type used by controller wiring
SessionRunner = Callable[[], None]
