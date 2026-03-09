"""Audio and STT adapters."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class AudioCaptureAdapter:
    def __init__(self, recognizer, chunk_manager=None):
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


class STTAdapter:
    def __init__(self, recognizer, chunk_manager=None):
        self._recognizer = recognizer
        self._chunk_manager = chunk_manager

    def transcribe(self, audio):
        if self._chunk_manager:
            result = self._chunk_manager.finalize()
            if result.is_partial:
                logger.warning(
                    "Partial transcription: %d/%d chunks failed",
                    result.failed_chunks,
                    result.total_chunks,
                )
            text = result.text
            return self._recognizer.filter_text(text) if text else None
        return self._recognizer.transcribe(audio)
