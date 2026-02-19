"""Metrics adapter wrapping latency tracker."""

from __future__ import annotations


class MetricsAdapter:
    def __init__(self, tracker):
        self._tracker = tracker

    def start_session(self) -> None:
        self._tracker.start_session()

    def measure(self, name: str, **kwargs):
        return self._tracker.measure(name, **kwargs)

    def end_session(self):
        return self._tracker.end_session()
