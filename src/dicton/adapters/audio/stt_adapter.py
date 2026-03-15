"""STT (speech-to-text) adapter."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


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
