"""Factory for selecting the correct text output implementation by platform."""

from __future__ import annotations

from ...shared.platform_utils import IS_LINUX, IS_MACOS, IS_WINDOWS
from .base import TextOutput


def get_text_output(
    selection_reader=None,
    *,
    paste_threshold_words: int = 10,
    debug: bool = False,
    clipboard_verify_delay_ms: int = 50,
    clipboard_max_retries: int = 5,
) -> TextOutput:
    """Return the appropriate TextOutput implementation for the current platform."""
    if IS_LINUX:
        from .linux import LinuxTextOutput

        return LinuxTextOutput(
            selection_reader,
            paste_threshold_words=paste_threshold_words,
            debug=debug,
            clipboard_verify_delay_ms=clipboard_verify_delay_ms,
            clipboard_max_retries=clipboard_max_retries,
        )
    if IS_WINDOWS:
        from .windows import WindowsTextOutput

        return WindowsTextOutput()
    if IS_MACOS:
        from .macos import MacOSTextOutput

        return MacOSTextOutput()
    from .fallback import PynputTextOutput

    return PynputTextOutput()
