"""Core ports (interfaces) for Dicton.

These protocols define the boundaries between the core orchestration
and platform/vendor-specific adapters. They are intentionally small and
capability-oriented to keep the core decoupled.
"""

from __future__ import annotations

from typing import Protocol, TYPE_CHECKING, runtime_checkable

if TYPE_CHECKING:
    from ..context_detector import ContextInfo


@runtime_checkable
class AudioCapture(Protocol):
    """Capture audio for a recording session."""

    def record(self):
        """Record audio until stopped; returns audio buffer or None."""

    def stop(self) -> None:
        """Stop recording and proceed to processing."""

    def cancel(self) -> None:
        """Cancel recording and discard audio."""


@runtime_checkable
class STTService(Protocol):
    """Speech-to-text transcription service."""

    def transcribe(self, audio) -> str | None:
        """Transcribe audio and return text."""


@runtime_checkable
class TextProcessor(Protocol):
    """Post-processing for transcribed text."""

    def process(
        self,
        text: str,
        mode,
        selected_text: str | None = None,
        context: "ContextInfo | None" = None,
    ) -> str | None:
        """Process text based on mode/context."""


@runtime_checkable
class TextOutput(Protocol):
    """Outputs text to the active application."""

    def output(
        self, text: str, mode, replace_selection: bool, context: "ContextInfo | None" = None
    ) -> None:
        """Emit text to the active app."""


@runtime_checkable
class UIFeedback(Protocol):
    """User-visible notifications."""

    def notify(self, title: str, message: str) -> None:
        """Display a notification."""


@runtime_checkable
class MetricsSink(Protocol):
    """Latency/metrics tracking."""

    def start_session(self) -> None:
        """Start a metrics session."""

    def measure(self, name: str, **kwargs):
        """Return a context manager for timing a block."""

    def end_session(self):
        """End the session and return a summary."""
