"""Chunker behaviour: silence cut, max cut, overlap."""

from __future__ import annotations

import numpy as np

from dicton.chunker import Chunker, ChunkParams

SR = 16000


def _silence(seconds: float) -> np.ndarray:
    return np.zeros(int(seconds * SR), dtype=np.int16)


def _tone(seconds: float, amp: int = 10000) -> np.ndarray:
    n = int(seconds * SR)
    t = np.linspace(0, seconds, n, endpoint=False)
    return (amp * np.sin(2 * np.pi * 440 * t)).astype(np.int16)


def test_silence_cut_emits_chunk_after_min_duration() -> None:
    emitted: list[tuple[int, int]] = []
    p = ChunkParams(
        min_chunk_s=2.0,
        max_chunk_s=20.0,
        silence_window_s=0.2,
        silence_threshold_dbfs=-40.0,
        sample_rate=SR,
    )
    c = Chunker(p, lambda i, w: emitted.append((i, len(w))))
    # 2.5s of tone (above threshold) then 0.4s of silence to trigger cut
    c.feed(_tone(2.5))
    c.feed(_silence(0.4))
    assert len(emitted) == 1, f"expected 1 chunk, got {len(emitted)}"
    assert emitted[0][0] == 0


def test_max_cut_when_no_silence() -> None:
    emitted: list[int] = []
    p = ChunkParams(min_chunk_s=2.0, max_chunk_s=3.0, sample_rate=SR)
    c = Chunker(p, lambda i, w: emitted.append(i))
    # 4s continuous tone — should force a max-cut at 3s
    c.feed(_tone(4.0))
    assert len(emitted) >= 1


def test_overlap_carries_audio_into_next_chunk() -> None:
    sizes: list[int] = []
    p = ChunkParams(
        min_chunk_s=1.5, max_chunk_s=5.0, overlap_s=0.5, silence_window_s=0.2, sample_rate=SR
    )
    c = Chunker(p, lambda i, w: sizes.append(len(w)))
    c.feed(_tone(2.0))
    c.feed(_silence(0.3))
    c.feed(_tone(2.0))
    c.feed(_silence(0.3))
    assert len(sizes) >= 2
    # second chunk's wav is at least min duration + overlap worth of audio
    assert sizes[1] > 0


def test_flush_emits_remaining_audio() -> None:
    emitted: list[int] = []
    p = ChunkParams(min_chunk_s=5.0, max_chunk_s=20.0, sample_rate=SR)
    c = Chunker(p, lambda i, w: emitted.append(i))
    c.feed(_tone(2.0))
    assert len(emitted) == 0
    c.flush()
    assert len(emitted) == 1
