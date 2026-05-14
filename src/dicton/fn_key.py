"""Linux Fn-key listener via evdev — optional, Linux-only.

The Fn key on ThinkPads is typically remapped by the kernel to KEY_WAKEUP
(143); on some Lenovo/ASUS models it surfaces as KEY_FN (464). We listen
on every keyboard-like device that exposes either code and emit
`on_press(is_double_tap)` on each key_down event. The pipeline state
machine decides what to do with it (double-tap only matters in IDLE;
any tap stops a RECORDING).
"""

from __future__ import annotations

import sys
import threading
import time
from collections.abc import Callable

# Fn keycodes seen across vendors.
#   143 = KEY_WAKEUP  (ThinkPad kernel remap of bare Fn)
#   464 = KEY_FN
#   465 = KEY_FN_ESC
#   466 = KEY_FN_F1
FN_KEYCODES = {143, 464, 465, 466}

DOUBLE_TAP_WINDOW_S = 0.3


class FnKeyListener:
    """Background thread that emits an `on_press(is_double_tap)` event per Fn
    key_down. State decisions belong to the caller."""

    def __init__(self, on_press: Callable[[bool], None]) -> None:
        self._on_press = on_press
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_release_ts = 0.0

    def start(self) -> bool:
        if sys.platform != "linux":
            return False
        try:
            import evdev  # noqa: F401
        except ImportError:
            return False
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop.set()

    def _handle_key_down(self) -> None:
        now = time.monotonic()
        is_double = (now - self._last_release_ts) < DOUBLE_TAP_WINDOW_S
        self._on_press(is_double)

    def _handle_key_up(self) -> None:
        self._last_release_ts = time.monotonic()

    def _run(self) -> None:
        try:
            from evdev import InputDevice, categorize, ecodes, list_devices
        except ImportError:
            return

        devices = []
        for path in list_devices():
            try:
                d = InputDevice(path)
            except OSError:
                continue
            caps = d.capabilities().get(ecodes.EV_KEY, [])
            # Skip pseudo-devices like Power Button that *also* expose
            # KEY_WAKEUP (143) but emit phantom events on suspend/resume.
            # Real keyboards advertise far more than the handful of system keys.
            if len(caps) < 10:
                continue
            if any(code in FN_KEYCODES for code in caps):
                devices.append(d)
        if not devices:
            return

        from select import select

        try:
            while not self._stop.is_set():
                r, _, _ = select(devices, [], [], 0.5)
                for d in r:
                    for event in d.read():
                        if event.type != ecodes.EV_KEY:
                            continue
                        if event.code not in FN_KEYCODES:
                            continue
                        key = categorize(event)
                        if key.keystate == key.key_down:
                            self._handle_key_down()
                        elif key.keystate == key.key_up:
                            self._handle_key_up()
        except OSError:
            return
