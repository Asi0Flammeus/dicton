"""Cross-platform clipboard + paste."""

from __future__ import annotations

import sys


def paste(text: str) -> None:
    """Place text on the clipboard and synthesise the paste keystroke."""
    if not text:
        return
    if sys.platform == "linux":
        from ._linux import _paste_linux

        _paste_linux(text)
    elif sys.platform == "darwin":
        from ._darwin import paste_darwin

        paste_darwin(text)
    elif sys.platform == "win32":
        from ._windows import paste_windows

        paste_windows(text)
    else:
        raise RuntimeError(f"unsupported platform: {sys.platform}")
