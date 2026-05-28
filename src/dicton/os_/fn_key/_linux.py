"""Linux Fn-key listener via evdev — optional, Linux-only.

The Fn key on ThinkPads is typically remapped by the kernel to KEY_WAKEUP
(143); on some Lenovo/ASUS models it surfaces as KEY_FN (464). We listen on
every keyboard-like device that exposes one of our trigger codes and emit a
bare `on_tap()` per key_down. Gesture meaning (double-tap vs noise) is decided
by `DoubleTapRecognizer`, not here.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable


def _keyboard_devices() -> list:
    """Open every keyboard-like evdev device.

    Skips pseudo-devices (Power Button etc.) that expose only a handful of
    system keys but emit phantom events on suspend/resume — real keyboards
    advertise far more than the system-key set.
    """
    from evdev import InputDevice, ecodes, list_devices

    devices = []
    for path in list_devices():
        try:
            d = InputDevice(path)
        except OSError:
            continue
        caps = d.capabilities().get(ecodes.EV_KEY, [])
        if len(caps) < 10:
            continue
        devices.append(d)
    return devices


def _friendly_name(code: int) -> str:
    """Human-readable config label for an evdev keycode (e.g. 'f8', 'fn')."""
    from evdev import ecodes

    name = ecodes.KEY.get(code)
    if isinstance(name, (list, tuple)):
        name = name[0]
    if not name:
        return f"key_{code}"
    label = name.removeprefix("KEY_").lower()
    # The kernel remaps bare Fn to WAKEUP on ThinkPads — present it as 'fn'.
    return "fn" if label in {"wakeup", "fn"} else label


def capture_keycode(timeout_s: float = 5.0) -> tuple[int, str] | None:
    """Listen on every keyboard and return (keycode, label) of the first real
    key pressed. Linux/evdev only; returns None on timeout or if evdev is
    unavailable. Drains pending events first so the Enter used to arm the
    prompt isn't captured, and ignores Enter/Esc."""
    try:
        from evdev import categorize, ecodes
    except ImportError:
        return None

    devices = _keyboard_devices()
    if not devices:
        return None

    from select import select

    ignore = {ecodes.KEY_ENTER, ecodes.KEY_KPENTER, ecodes.KEY_ESC}

    # Drain whatever is already queued (e.g. the Enter keypress).
    drain_until = time.monotonic() + 0.4
    while time.monotonic() < drain_until:
        r, _, _ = select(devices, [], [], 0.05)
        for d in r:
            try:
                for _ in d.read():
                    pass
            except OSError:
                pass

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        r, _, _ = select(devices, [], [], 0.2)
        for d in r:
            try:
                events = list(d.read())
            except OSError:
                continue
            for event in events:
                if event.type != ecodes.EV_KEY:
                    continue
                key = categorize(event)
                if key.keystate != key.key_down:
                    continue
                if event.code in ignore:
                    continue
                return event.code, _friendly_name(event.code)
    return None


class LinuxFnKeyListener:
    """Background thread that emits a bare `on_tap()` per trigger key_down.
    Gesture meaning is decided downstream by DoubleTapRecognizer."""

    def __init__(
        self,
        on_tap: Callable[[], None],
        keycodes: set[int],
    ) -> None:
        self._on_tap = on_tap
        self._keycodes = keycodes
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> bool:
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
            from evdev import categorize, ecodes
        except ImportError:
            return

        # Keep only devices that actually expose one of our trigger codes.
        devices = [
            d
            for d in _keyboard_devices()
            if any(code in self._keycodes for code in d.capabilities().get(ecodes.EV_KEY, []))
        ]
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
                        if event.code not in self._keycodes:
                            continue
                        key = categorize(event)
                        if key.keystate == key.key_down:
                            self._on_tap()
        except OSError:
            return
