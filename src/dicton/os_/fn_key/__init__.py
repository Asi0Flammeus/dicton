"""Fn-key listener façade.

Public API: ``FnKeyListener``, ``capture_keycode``, ``FN_KEYCODES``. The
Linux backend (evdev) is the only one that actually does anything;
elsewhere ``FnKeyListener.start()`` returns ``False`` and
``capture_keycode`` returns ``None``.
"""

from __future__ import annotations

import sys
from collections.abc import Callable

# Fn keycodes seen across vendors.
#   143 = KEY_WAKEUP  (ThinkPad kernel remap of bare Fn)
#   464 = KEY_FN
#   465 = KEY_FN_ESC
#   466 = KEY_FN_F1
FN_KEYCODES = {143, 464, 465, 466}


def capture_keycode(timeout_s: float = 5.0) -> tuple[int, str] | None:
    """Listen on every keyboard and return (keycode, label) of the first real
    key pressed. Linux/evdev only; returns None on timeout or if evdev is
    unavailable."""
    if sys.platform != "linux":
        return None
    from ._linux import capture_keycode as _capture

    return _capture(timeout_s)


class FnKeyListener:
    """Background thread that emits a bare `on_tap()` per trigger key_down.
    Gesture meaning is decided downstream by DoubleTapRecognizer."""

    def __init__(
        self,
        on_tap: Callable[[], None],
        keycodes: set[int] | None = None,
    ) -> None:
        self._on_tap = on_tap
        self._keycodes = keycodes or FN_KEYCODES
        self._impl: object | None = None

    def start(self) -> bool:
        if sys.platform != "linux":
            return False
        from ._linux import LinuxFnKeyListener

        self._impl = LinuxFnKeyListener(self._on_tap, self._keycodes)
        return self._impl.start()

    def stop(self) -> None:
        if self._impl is not None:
            self._impl.stop()  # type: ignore[attr-defined]
