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
    if sys.platform != "linux":
        return None
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


class FnKeyListener:
    """Background thread that emits an `on_press(is_double_tap)` event per Fn
    key_down. State decisions belong to the caller."""

    def __init__(
        self,
        on_press: Callable[[bool], None],
        keycodes: set[int] | None = None,
    ) -> None:
        self._on_press = on_press
        self._keycodes = keycodes or FN_KEYCODES
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
                            self._handle_key_down()
                        elif key.keystate == key.key_up:
                            self._handle_key_up()
        except OSError:
            return
