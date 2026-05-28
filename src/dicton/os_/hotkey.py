"""OS-specific pynput hotkey helpers."""

from __future__ import annotations

import sys
from typing import Any

from pynput import keyboard


def pynput_primary_key() -> Any | None:
    """Return the OS-native primary key object when pynput exposes one."""
    if sys.platform == "darwin":
        return getattr(keyboard.Key, "fn", None)
    return None
