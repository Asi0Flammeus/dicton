"""Linux Fn-key listener via evdev — optional, Linux-only.

The Fn key is not surfaced to userland by most laptops, but on a handful of
Lenovo/ASUS models it is exposed as a regular evdev keycode on the keyboard
device. We listen for it and call the same handler as pynput.
"""

from __future__ import annotations

import sys
import threading
from collections.abc import Callable

# Common Fn keycodes seen across vendors. evdev exposes them as ints.
FN_KEYCODES = {464, 0x1D1, 0x1D2}


class FnKeyListener:
    """Background thread that calls on_press / on_release for the Fn key."""

    def __init__(
        self,
        on_press: Callable[[], None],
        on_release: Callable[[], None],
    ) -> None:
        self._on_press = on_press
        self._on_release = on_release
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

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
                            self._on_press()
                        elif key.keystate == key.key_up:
                            self._on_release()
        except OSError:
            return
