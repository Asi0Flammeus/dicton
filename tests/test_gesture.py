"""Double-tap recognizer: clean taptap fires, single and bursts are noise."""

from __future__ import annotations

import threading
import time

from dicton.fn_key import DoubleTapRecognizer

WINDOW_S = 0.05  # tight window keeps the tests fast and deterministic
SETTLE_PAD = 0.04  # extra time we wait past the window for the timer to fire


class _Sink:
    def __init__(self) -> None:
        self.fired = 0
        self._lock = threading.Lock()

    def __call__(self) -> None:
        with self._lock:
            self.fired += 1

    def wait(self, expected: int, timeout: float) -> int:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._lock:
                if self.fired >= expected:
                    return self.fired
            time.sleep(0.005)
        with self._lock:
            return self.fired


def _wait_settle() -> None:
    """Sleep long enough for the recognizer's settle timer to fire once."""
    time.sleep(WINDOW_S + SETTLE_PAD)


def test_single_tap_is_ignored() -> None:
    sink = _Sink()
    rec = DoubleTapRecognizer(sink, window_s=WINDOW_S)
    rec.feed_tap()
    _wait_settle()
    assert sink.fired == 0


def test_double_tap_fires_once() -> None:
    sink = _Sink()
    rec = DoubleTapRecognizer(sink, window_s=WINDOW_S)
    rec.feed_tap()
    time.sleep(WINDOW_S / 3)  # well within the window
    rec.feed_tap()
    assert sink.wait(1, timeout=0.3) == 1


def test_three_rapid_taps_is_noise() -> None:
    """The mitraille case: bursts of 3+ taps must NOT trigger anything."""
    sink = _Sink()
    rec = DoubleTapRecognizer(sink, window_s=WINDOW_S)
    for _ in range(3):
        rec.feed_tap()
        time.sleep(WINDOW_S / 4)
    _wait_settle()
    assert sink.fired == 0


def test_five_rapid_taps_is_noise() -> None:
    sink = _Sink()
    rec = DoubleTapRecognizer(sink, window_s=WINDOW_S)
    for _ in range(5):
        rec.feed_tap()
        time.sleep(WINDOW_S / 4)
    _wait_settle()
    assert sink.fired == 0


def test_two_taps_far_apart_are_two_singles_ignored() -> None:
    """Gap > window between taps -> each tap settles alone as a single."""
    sink = _Sink()
    rec = DoubleTapRecognizer(sink, window_s=WINDOW_S)
    rec.feed_tap()
    _wait_settle()
    rec.feed_tap()
    _wait_settle()
    assert sink.fired == 0


def test_two_consecutive_double_taps_each_fire() -> None:
    sink = _Sink()
    rec = DoubleTapRecognizer(sink, window_s=WINDOW_S)
    # First taptap
    rec.feed_tap()
    time.sleep(WINDOW_S / 3)
    rec.feed_tap()
    assert sink.wait(1, timeout=0.3) == 1
    # Quiet, then second taptap
    _wait_settle()
    rec.feed_tap()
    time.sleep(WINDOW_S / 3)
    rec.feed_tap()
    assert sink.wait(2, timeout=0.3) == 2


def test_stop_cancels_pending_settle() -> None:
    sink = _Sink()
    rec = DoubleTapRecognizer(sink, window_s=WINDOW_S)
    rec.feed_tap()
    rec.feed_tap()
    rec.stop()
    _wait_settle()
    # stop() cancels the pending settle so the would-be double-tap never fires.
    assert sink.fired == 0
