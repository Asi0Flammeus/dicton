"""Cross-platform clipboard + paste.

Linux: prefers wl-copy + wtype on Wayland, falls back to xclip + xdotool on
X11. macOS: pbcopy + AppleScript Cmd+V. Windows: SetClipboardData via the
`clip` command, then SendInput Ctrl+V via ctypes.

Restores the prior clipboard content after pasting.
"""

from __future__ import annotations

import sys


def paste(text: str) -> None:
    """Place text on the clipboard and synthesise the paste keystroke."""
    if not text:
        return
    if sys.platform == "linux":
        from ._linux import paste_linux

        paste_linux(text)
    elif sys.platform == "darwin":
        from ._darwin import paste_darwin

        paste_darwin(text)
    elif sys.platform == "win32":
        from ._windows import paste_windows

        paste_windows(text)
    else:
        raise RuntimeError(f"unsupported platform: {sys.platform}")
