"""Dicton - cross-platform voice-to-text dictation."""

__version__ = "1.8.1"
__author__ = "asi0 flammeus"
__description__ = "Voice-to-text dictation with direct transcription and translation"

__all__ = ["main", "__version__"]


def __getattr__(name: str):
    """Lazy import to avoid triggering pynput initialization on package import.

    This allows importing dicton.shared.config or dicton.shared.platform_utils
    without requiring an X display, which is needed for CI/headless environments.
    """
    if name == "main":
        from .interfaces.cli import main

        return main
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
