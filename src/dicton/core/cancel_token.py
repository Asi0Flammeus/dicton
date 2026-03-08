"""Cancellation token for in-flight sessions."""

from __future__ import annotations

import threading


class CancelToken:
    def __init__(self):
        self._event = threading.Event()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def cancel(self) -> None:
        self._event.set()

    def reset(self) -> None:
        self._event.clear()
