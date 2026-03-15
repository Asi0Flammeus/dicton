"""Factory for selecting the correct SelectionReader implementation by platform."""

from __future__ import annotations

from ...shared.platform_utils import IS_LINUX, IS_MACOS, IS_WAYLAND, IS_WINDOWS
from .selection_base import NullSelectionReader, SelectionReader


def get_selection_reader() -> SelectionReader:
    """Return the appropriate SelectionReader for the current platform."""
    if IS_LINUX:
        if IS_WAYLAND:
            from .selection_wayland import WaylandSelectionReader

            return WaylandSelectionReader()
        from .selection_x11 import X11SelectionReader

        return X11SelectionReader()
    if IS_WINDOWS:
        from .selection_windows import WindowsSelectionReader

        return WindowsSelectionReader()
    if IS_MACOS:
        from .selection_macos import MacOSSelectionReader

        return MacOSSelectionReader()
    return NullSelectionReader()
