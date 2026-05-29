"""pynput hotkey helpers that need OS-specific resolution.

Only pynput's macOS backend exposes ``Key.fn``. Windows and Linux X11
backends don't define it — Linux uses evdev (KEY_WAKEUP on ThinkPads,
KEY_FN elsewhere), Windows has no userland Fn path at all.
"""

from __future__ import annotations

import sys


def pynput_primary_key() -> object | None:
    """Return the pynput ``Key.fn`` constant on macOS, ``None`` elsewhere.

    ``getattr`` keeps this robust if pynput's API shifts.
    """
    if sys.platform != "darwin":
        return None
    from pynput import keyboard

    return getattr(keyboard.Key, "fn", None)
