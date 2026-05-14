"""Silence-aware recording chunker."""

from __future__ import annotations

import audioop
import io
import math
import wave
from dataclasses import dataclass


@dataclass(slots=True)
class ChunkSettings:
    sample_rate: int = 16_000
    frame_ms: int = 50
    min_chunk_s: float = 6.0
    max_chunk_s: float = 20.0
    overlap_s: float = 0.4
    silence_threshold_dbfs: float = -40.0
    silence_window_s: float = 0.35


class Chunker:
    def __init__(self, settings: ChunkSettings | None = None) -> None:
        self.settings = settings or ChunkSettings()
        self.frames: list[bytes] = []
        self.boundary = 0
        self.silent_run = 0
        self.frame_s = self.settings.frame_ms / 1000
        self.silence_frames = max(1, round(self.settings.silence_window_s / self.frame_s))
        self.overlap_frames = max(0, round(self.settings.overlap_s / self.frame_s))

    def reset(self) -> None:
        self.frames.clear()
        self.boundary = 0
        self.silent_run = 0

    def feed(self, pcm16: bytes) -> bytes | None:
        self.frames.append(pcm16)
        self.silent_run = (
            self.silent_run + 1 if self._dbfs(pcm16) < self.settings.silence_threshold_dbfs else 0
        )
        pending = len(self.frames) - self.boundary
        duration = pending * self.frame_s
        if self.silent_run >= self.silence_frames and duration >= self.settings.min_chunk_s:
            return self._cut(len(self.frames) - self.silent_run)
        if duration >= self.settings.max_chunk_s:
            return self._cut(len(self.frames))
        return None

    def flush(self) -> bytes | None:
        if self.boundary >= len(self.frames):
            return None
        return self._cut(len(self.frames))

    def _cut(self, cut_point: int) -> bytes | None:
        cut_point = max(self.boundary, cut_point)
        selected = self.frames[self.boundary : cut_point]
        self.boundary = max(cut_point - self.overlap_frames, self.boundary)
        self.silent_run = 0
        return pcm_to_wav(b"".join(selected), self.settings.sample_rate) if selected else None

    @staticmethod
    def _dbfs(pcm16: bytes) -> float:
        if not pcm16:
            return -120.0
        rms = audioop.rms(pcm16, 2)
        return 20 * math.log10(max(rms, 1) / 32768)


def pcm_to_wav(pcm16: bytes, sample_rate: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm16)
    return buf.getvalue()
