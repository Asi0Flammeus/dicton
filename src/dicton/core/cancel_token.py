"""Cancellation token for in-flight sessions."""

from __future__ import annotations


class CancelToken:
    def __init__(self):
        self._cancelled = False

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    def cancel(self) -> None:
        self._cancelled = True

    def reset(self) -> None:
        self._cancelled = False
