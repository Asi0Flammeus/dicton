"""Regression tests for FN hotkey callback ordering."""

from __future__ import annotations

import threading
import time

from dicton.adapters.input.fn.handler import FnKeyHandler
from dicton.shared.processing_mode import ProcessingMode


def test_toggle_callbacks_are_delivered_in_order():
    calls: list[str] = []
    start_entered = threading.Event()
    allow_start_to_finish = threading.Event()
    stop_called = threading.Event()

    def on_start(mode: ProcessingMode) -> None:
        assert mode == ProcessingMode.BASIC
        start_entered.set()
        allow_start_to_finish.wait(timeout=1.0)
        calls.append("start")

    def on_stop() -> None:
        calls.append("stop")
        stop_called.set()

    handler = FnKeyHandler(on_start_recording=on_start, on_stop_recording=on_stop)

    try:
        handler._on_custom_hotkey_down()
        assert start_entered.wait(timeout=1.0)

        handler._on_custom_hotkey_down()
        time.sleep(0.05)

        # The queued stop must wait for the earlier start callback to finish.
        assert calls == []

        allow_start_to_finish.set()
        assert stop_called.wait(timeout=1.0)
        assert calls == ["start", "stop"]
    finally:
        allow_start_to_finish.set()
        handler.stop()


def test_fn_mode_detection_blocks_advanced_modes_when_disabled():
    handler = FnKeyHandler(enable_advanced_modes=False)

    try:
        handler._alt_pressed = True
        assert handler._detect_mode() == ProcessingMode.BASIC

        handler._alt_pressed = False
        handler._space_pressed = True
        assert handler._detect_mode() == ProcessingMode.BASIC

        handler._space_pressed = False
        handler._ctrl_pressed = True
        handler._shift_pressed = True
        assert handler._detect_mode() == ProcessingMode.TRANSLATION
    finally:
        handler.stop()


def test_fn_mode_detection_routes_advanced_modes_when_enabled():
    handler = FnKeyHandler(enable_advanced_modes=True)

    try:
        handler._alt_pressed = True
        assert handler._detect_mode() == ProcessingMode.REFORMULATION

        handler._alt_pressed = False
        handler._space_pressed = True
        assert handler._detect_mode() == ProcessingMode.RAW

        handler._space_pressed = False
        handler._ctrl_pressed = True
        assert handler._detect_mode() == ProcessingMode.TRANSLATION

        handler._shift_pressed = True
        assert handler._detect_mode() == ProcessingMode.TRANSLATE_REFORMAT
    finally:
        handler.stop()
