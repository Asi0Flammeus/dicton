"""Factory for selecting the correct text output implementation by platform."""

from __future__ import annotations

from ..platform_utils import IS_LINUX, IS_MACOS, IS_WINDOWS
from .base import TextOutput


def get_text_output(selection_reader=None) -> TextOutput:
    """Return the appropriate TextOutput implementation for the current platform."""
    if IS_LINUX:
        from .linux import LinuxTextOutput

        return LinuxTextOutput(selection_reader)
    if IS_WINDOWS:
        from .windows import WindowsTextOutput

        return WindowsTextOutput()
    if IS_MACOS:
        from .macos import MacOSTextOutput

        return MacOSTextOutput()
    from .fallback import PynputTextOutput

    return PynputTextOutput()
