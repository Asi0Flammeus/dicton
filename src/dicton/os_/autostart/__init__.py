"""Cross-platform autostart toggle.

Linux: systemd --user unit. macOS: ~/Library/LaunchAgents plist. Windows:
HKCU Run registry key. Wizard calls `enable_autostart()`; the user can
disable from the same wizard later.
"""

from __future__ import annotations

import sys


def enable_autostart() -> bool:
    if sys.platform == "linux":
        from ._linux import enable as _enable

        return _enable()
    if sys.platform == "darwin":
        from ._darwin import enable as _enable

        return _enable()
    if sys.platform == "win32":
        from ._windows import enable as _enable

        return _enable()
    return False


def disable_autostart() -> bool:
    if sys.platform == "linux":
        from ._linux import disable as _disable

        return _disable()
    if sys.platform == "darwin":
        from ._darwin import disable as _disable

        return _disable()
    if sys.platform == "win32":
        from ._windows import disable as _disable

        return _disable()
    return False
