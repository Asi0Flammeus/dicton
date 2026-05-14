"""Minimal Linux Fn-key detector using evdev when available."""

from __future__ import annotations

import sys
from collections.abc import Callable


def watch_fn(callback: Callable[[], None], scancode: int | None = None) -> None:
    if not sys.platform.startswith("linux"):
        return
    try:
        from evdev import InputDevice, categorize, ecodes, list_devices
    except ImportError:
        return
    for path in list_devices():
        dev = InputDevice(path)
        caps = dev.capabilities().get(ecodes.EV_KEY, [])
        if scancode and scancode not in caps:
            continue
        for event in dev.read_loop():
            if event.type == ecodes.EV_KEY:
                key = categorize(event)
                if key.keystate == key.key_down and (scancode is None or key.scancode == scancode):
                    callback()
