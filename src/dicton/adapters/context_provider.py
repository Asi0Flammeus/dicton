"""Context provider adapter."""

from __future__ import annotations

from ..context_detector import get_context_detector


class ContextProviderAdapter:
    def __init__(self, detector=None):
        self._detector = detector or get_context_detector()

    def get_context(self):
        return self._detector.get_context()
