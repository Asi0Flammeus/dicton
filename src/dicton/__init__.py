"""Dicton - Cross-platform voice-to-text transcription with ElevenLabs"""

__version__ = "1.0.0"
__author__ = "asi0 flammeus"
__description__ = "Cross-platform voice-to-text transcription with ElevenLabs"

__all__ = ["main", "Dicton", "__version__"]


def __getattr__(name: str):
    """Lazy import to avoid triggering pynput initialization on package import.

    This allows importing dicton.config or dicton.platform_utils without
    requiring an X display, which is needed for CI/headless environments.
    """
    if name == "Dicton":
        from .main import Dicton

        return Dicton
    if name == "main":
        from .main import main

        return main
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
