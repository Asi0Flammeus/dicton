"""Silence-based audio chunker — emits chunks while recording is in progress.

The pipeline feeds raw int16 PCM frames in. The chunker tracks RMS in dBFS,
cuts at silence boundaries (with overlap), and yields wav-encoded chunks via
a callback so the pipeline can fire STT requests concurrently. At hotkey-up,
`flush()` emits the queue as the final chunk.

Ported from the previous `chunk_manager.py`; defaults are the empirically
tuned values from the refonte-v2 spec.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from .stt import pcm16_to_wav


@dataclass
class ChunkParams:
    min_chunk_s: float = 6.0
    max_chunk_s: float = 20.0
    overlap_s: float = 0.4
    silence_threshold_dbfs: float = -40.0
    silence_window_s: float = 0.35
    sample_rate: int = 16000


EmitFn = Callable[[int, bytes], None]


def _rms_dbfs(samples: np.ndarray) -> float:
    if samples.size == 0:
        return -math.inf
    data = samples.astype(np.float32)
    data = data - np.mean(data)
    rms = float(np.sqrt(np.mean(data * data)))
    if rms <= 1.0:
        return -math.inf
    return 20.0 * math.log10(rms / 32768.0)


class Chunker:
    """Maintains a rolling int16 PCM buffer and cuts at silence boundaries."""

    def __init__(self, params: ChunkParams, on_chunk: EmitFn) -> None:
        self.p = params
        self._on_chunk = on_chunk
        self._buf = np.empty(0, dtype=np.int16)
        self._boundary = 0
        self._silent_samples = 0
        self._chunk_count = 0
        self._frames_emitted = False

    @property
    def chunks_emitted(self) -> int:
        return self._chunk_count

    @property
    def retained_samples(self) -> int:
        return self._buf.size

    def reset(self) -> None:
        self._buf = np.empty(0, dtype=np.int16)
        self._boundary = 0
        self._silent_samples = 0
        self._chunk_count = 0
        self._frames_emitted = False

    def feed(self, frame: np.ndarray) -> None:
        """Append a frame of int16 mono samples and possibly emit a chunk."""
        if frame.dtype != np.int16:
            frame = frame.astype(np.int16)
        self._buf = np.concatenate([self._buf, frame])

        level = _rms_dbfs(frame)
        if level < self.p.silence_threshold_dbfs:
            self._silent_samples += frame.size
        else:
            self._silent_samples = 0

        unchunked = self._buf.size - self._boundary
        duration_s = unchunked / self.p.sample_rate
        silence_s = self._silent_samples / self.p.sample_rate

        if silence_s >= self.p.silence_window_s and duration_s >= self.p.min_chunk_s:
            cut = self._buf.size - self._silent_samples
            self._emit(cut)
        elif duration_s >= self.p.max_chunk_s:
            self._emit(self._buf.size)

    def flush(self) -> None:
        """Emit whatever audio is left as a final chunk."""
        remaining = self._buf.size - self._boundary
        # Skip a tiny tail (< 0.3s) — Whisper struggles below that anyway,
        # but only if we already produced at least one chunk this session.
        if remaining / self.p.sample_rate < 0.3 and self._frames_emitted:
            return
        if remaining <= 0:
            return
        self._emit(self._buf.size)

    def _emit(self, cut: int) -> None:
        slice_samples = self._buf[self._boundary : cut]
        if slice_samples.size == 0:
            return
        wav = pcm16_to_wav(slice_samples, self.p.sample_rate)
        chunk_id = self._chunk_count
        self._chunk_count += 1
        self._frames_emitted = True

        overlap = int(self.p.overlap_s * self.p.sample_rate)
        keep_from = max(cut - overlap, self._boundary)
        if keep_from > 0:
            self._buf = self._buf[keep_from:].copy()
            self._boundary = 0
        else:
            self._boundary = keep_from

        self._silent_samples = 0
        self._on_chunk(chunk_id, wav)
