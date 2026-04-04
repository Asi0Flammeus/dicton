"""Metrics adapter wrapping latency tracker."""

from __future__ import annotations

from contextlib import AbstractContextManager


class MetricsAdapter:
    """Adapter satisfying :class:`~dicton.core.ports.MetricsSink`."""

    def __init__(self, tracker) -> None:
        self._tracker = tracker

    def start_session(self) -> None:
        self._tracker.start_session()

    def measure(self, name: str, **kwargs) -> AbstractContextManager[None]:
        return self._tracker.measure(name, **kwargs)

    def end_session(self):
        return self._tracker.end_session()
