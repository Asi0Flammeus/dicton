"""Pure-Python gesture recognition. No OS coupling."""

from __future__ import annotations

import threading
from collections.abc import Callable

DOUBLE_TAP_WINDOW_S = 0.3


class DoubleTapRecognizer:
    """Turns a stream of taps into clean double-tap gestures.

    A gesture is "settled" once no new tap arrives for ``window_s`` after the
    last one (the timer is reset on every tap). Only a settled count of
    **exactly two** fires ``on_double_tap``; a single tap, or a burst of three
    or more rapid taps ("mitraille"), is discarded as noise. This is what makes
    a deliberate tap-tap meaningful while ignoring stray presses and key
    chatter.
    """

    def __init__(
        self,
        on_double_tap: Callable[[], None],
        window_s: float = DOUBLE_TAP_WINDOW_S,
    ) -> None:
        self._cb = on_double_tap
        self._window = window_s
        self._count = 0
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()

    def feed_tap(self) -> None:
        with self._lock:
            self._count += 1
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(self._window, self._settle)
            self._timer.daemon = True
            self._timer.start()

    def _settle(self) -> None:
        with self._lock:
            count = self._count
            self._count = 0
            self._timer = None
        if count == 2:
            self._cb()

    def stop(self) -> None:
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
