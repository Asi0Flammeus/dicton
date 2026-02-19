"""Audio and STT adapters."""

from __future__ import annotations


class AudioCaptureAdapter:
    def __init__(self, recognizer):
        self._recognizer = recognizer

    def record(self):
        return self._recognizer.record()

    def stop(self) -> None:
        self._recognizer.stop()

    def cancel(self) -> None:
        self._recognizer.cancel()


class STTAdapter:
    def __init__(self, recognizer):
        self._recognizer = recognizer

    def transcribe(self, audio):
        return self._recognizer.transcribe(audio)
