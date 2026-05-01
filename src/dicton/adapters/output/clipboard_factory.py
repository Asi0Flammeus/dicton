"""Factory for selecting the correct Clipboard implementation by platform."""

from __future__ import annotations

from ...shared.platform_utils import IS_LINUX, IS_MACOS, IS_WAYLAND, IS_WINDOWS
from .clipboard_base import Clipboard, NullClipboard


def get_clipboard(*, debug: bool = False) -> Clipboard:
    """Return the appropriate Clipboard for the current platform."""
    if IS_LINUX:
        if IS_WAYLAND:
            from .clipboard_wayland import WaylandClipboard

            return WaylandClipboard(debug=debug)
        from .clipboard_x11 import X11Clipboard

        return X11Clipboard(debug=debug)
    if IS_WINDOWS:
        from .clipboard_windows import WindowsClipboard

        return WindowsClipboard()
    if IS_MACOS:
        from .clipboard_macos import MacOSClipboard

        return MacOSClipboard()
    return NullClipboard()
