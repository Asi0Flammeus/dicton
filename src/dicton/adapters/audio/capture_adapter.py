"""Audio capture adapter."""

from __future__ import annotations


class AudioCaptureAdapter:
    """Adapter satisfying :class:`~dicton.core.ports.AudioCapture`."""

    def __init__(self, recognizer, chunk_manager=None) -> None:
        self._recognizer = recognizer
        self._chunk_manager = chunk_manager

    def record(self):
        if self._chunk_manager:
            self._chunk_manager.start_session()
            return self._recognizer.record(on_chunk=self._chunk_manager.feed_chunk)
        return self._recognizer.record()

    def stop(self) -> None:
        self._recognizer.stop()

    def cancel(self) -> None:
        self._recognizer.cancel()
        if self._chunk_manager:
            self._chunk_manager.cancel()
