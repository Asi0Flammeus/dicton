"""Cross-platform autostart toggle."""

from __future__ import annotations

import sys


def enable_autostart() -> bool:
    if sys.platform == "linux":
        from . import _linux

        return _linux.enable()
    if sys.platform == "darwin":
        from . import _darwin

        return _darwin.enable()
    if sys.platform == "win32":
        from . import _windows

        return _windows.enable()
    return False


def disable_autostart() -> bool:
    if sys.platform == "linux":
        from . import _linux

        return _linux.disable()
    if sys.platform == "darwin":
        from . import _darwin

        return _darwin.disable()
    if sys.platform == "win32":
        from . import _windows

        return _windows.disable()
    return False
