"""Unit tests for src.dicton.chunk_manager."""

import os
import threading
from unittest.mock import MagicMock

import numpy as np
import pytest

from dicton.chunk_manager import ChunkConfig, ChunkManager
from dicton.stt_provider import TranscriptionResult

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
CHUNK_SIZE = 1024
SAMPLE_RATE = 16000
BYTES_PER_FRAME = CHUNK_SIZE * 2  # int16 = 2 bytes per sample
SILENCE_FRAME = b"\x00" * BYTES_PER_FRAME


def _speech_frame() -> bytes:
    """Return random bytes that produce RMS >> 0.03 (speech-level audio)."""
    return os.urandom(BYTES_PER_FRAME)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_stt():
    provider = MagicMock()
    provider.transcribe.return_value = TranscriptionResult(text="chunk text")
    return provider


@pytest.fixture
def chunk_config():
    return ChunkConfig(
        enabled=True,
        threshold_s=20.0,
        silence_threshold=0.03,
        silence_window_s=0.3,
        lookback_s=5.0,
        chunk_size=1024,
        sample_rate=16000,
        stt_timeout=120.0,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_short_recording_no_chunks(mock_stt, chunk_config):
    """<20 s of audio does not dispatch any chunks and never calls STT."""
    manager = ChunkManager(mock_stt, chunk_config)
    manager.start_session()
    # 200 frames × 0.064 s/frame = 12.8 s < 20 s threshold
    for _ in range(200):
        manager.feed_chunk(SILENCE_FRAME)
    assert not manager.has_chunks
    mock_stt.transcribe.assert_not_called()


def test_threshold_triggers_chunk(mock_stt, chunk_config):
    """25 s of audio triggers exactly one chunk dispatch."""
    manager = ChunkManager(mock_stt, chunk_config)
    manager.start_session()
    # 391 frames × 0.064 s/frame ≈ 25 s > 20 s threshold
    for _ in range(391):
        manager.feed_chunk(_speech_frame())
    assert manager.has_chunks
    for f in manager._futures:
        f.result(timeout=5.0)
    assert mock_stt.transcribe.call_count == 1


def test_silence_detection_finds_gap(mock_stt, chunk_config):
    """Silence gap inside a chunk causes the cut point to align with silence."""
    manager = ChunkManager(mock_stt, chunk_config)
    manager.start_session()
    # Frames 0–279: speech; frames 280–329: silence
    for i in range(330):
        frame = SILENCE_FRAME if i >= 280 else _speech_frame()
        manager.feed_chunk(frame)
    assert manager.has_chunks
    for f in manager._futures:
        f.result(timeout=5.0)
    wav_bytes = mock_stt.transcribe.call_args[0][0]
    # WAV header = 44 bytes; remaining bytes are int16 PCM (2 bytes/sample)
    wav_audio_bytes = len(wav_bytes) - 44
    frames_sent = wav_audio_bytes // BYTES_PER_FRAME
    # silence_window_s=0.3 → 4 consecutive silent frames needed;
    # cut lands at frame ~309 (silence starts at 280, scanner finds run at 309)
    assert 275 <= frames_sent <= 315


def test_no_silence_fallback(mock_stt, chunk_config):
    """Continuous noise with no silence falls back to cutting at the threshold position."""
    manager = ChunkManager(mock_stt, chunk_config)
    manager.start_session()
    for _ in range(391):
        manager.feed_chunk(_speech_frame())
    assert manager.has_chunks
    for f in manager._futures:
        f.result(timeout=5.0)
    wav_bytes = mock_stt.transcribe.call_args[0][0]
    wav_audio_bytes = len(wav_bytes) - 44
    frames_sent = wav_audio_bytes // BYTES_PER_FRAME
    # Fallback: cut at int(20.0 × 16000 / 1024) = 312 frames
    assert frames_sent == 312


def test_finalize_concatenates_in_order(mock_stt, chunk_config):
    """finalize() joins all chunk texts (dispatched + final) separated by spaces."""
    manager = ChunkManager(mock_stt, chunk_config)
    manager.start_session()
    # 700 frames → 2 dispatches (at frames 313 and 625) + remaining final chunk
    for _ in range(700):
        manager.feed_chunk(_speech_frame())
    assert manager.has_chunks
    dummy_audio = np.zeros(100, dtype=np.float32)
    result = manager.finalize(dummy_audio)
    assert result is not None
    # 3 chunks each returning "chunk text"; all three present in joined output
    assert mock_stt.transcribe.call_count == 3
    assert result.count("chunk text") == 3


def test_cancel_discards_all(mock_stt, chunk_config):
    """After cancel(), finalize() returns None regardless of buffered chunks."""
    manager = ChunkManager(mock_stt, chunk_config)
    manager.start_session()
    for _ in range(391):
        manager.feed_chunk(_speech_frame())
    assert manager.has_chunks
    manager.cancel()
    dummy_audio = np.zeros(100, dtype=np.float32)
    result = manager.finalize(dummy_audio)
    assert result is None


def test_provider_error_partial_results(mock_stt, chunk_config):
    """A chunk that raises during transcription is skipped; other chunks contribute."""
    call_count = [0]
    lock = threading.Lock()

    def side_effect(_audio):
        with lock:
            n = call_count[0]
            call_count[0] += 1
        if n == 1:
            raise RuntimeError("STT provider failure")
        return TranscriptionResult(text=f"text{n}")

    mock_stt.transcribe.side_effect = side_effect
    manager = ChunkManager(mock_stt, chunk_config)
    manager.start_session()
    for _ in range(700):
        manager.feed_chunk(_speech_frame())
    dummy_audio = np.zeros(100, dtype=np.float32)
    result = manager.finalize(dummy_audio)
    assert mock_stt.transcribe.call_count == 3
    assert result is not None
    # Two successful chunks → two text segments joined by a single space
    assert len(result.split(" ")) == 2


def test_start_session_resets_state(mock_stt, chunk_config):
    """start_session() fully resets internal state between recordings."""
    manager = ChunkManager(mock_stt, chunk_config)
    manager.start_session()
    for _ in range(391):
        manager.feed_chunk(_speech_frame())
    dummy_audio = np.zeros(100, dtype=np.float32)
    manager.finalize(dummy_audio)
    manager.start_session()
    assert manager._frames == []
    assert manager._futures == []
    assert manager._chunk_boundary == 0
    assert not manager.has_chunks


def test_rms_computation(mock_stt, chunk_config):
    """_compute_rms returns expected values for silence and known amplitudes."""
    manager = ChunkManager(mock_stt, chunk_config)
    # Silence: all zeros → RMS = 0
    assert manager._compute_rms(SILENCE_FRAME) == 0.0
    # Max int16 amplitude (32767) → RMS = 32767 / 8000
    max_val = np.full(CHUNK_SIZE, 32767, dtype=np.int16).tobytes()
    assert abs(manager._compute_rms(max_val) - 32767.0 / 8000.0) < 1e-4
    # Min int16 amplitude (-32768) → RMS = 32768 / 8000
    min_val = np.full(CHUNK_SIZE, -32768, dtype=np.int16).tobytes()
    assert abs(manager._compute_rms(min_val) - 32768.0 / 8000.0) < 1e-4


def test_short_final_chunk_skipped(mock_stt, chunk_config):
    """Remaining audio < 0.5 s after the last dispatch is not sent to STT."""
    manager = ChunkManager(mock_stt, chunk_config)
    manager.start_session()
    # Dispatch at frame 313 (boundary → 312), then leave 5 frames = 0.32 s < 0.5 s
    for _ in range(317):
        manager.feed_chunk(_speech_frame())
    assert manager.has_chunks
    for f in manager._futures:
        f.result(timeout=5.0)
    calls_before = mock_stt.transcribe.call_count
    dummy_audio = np.zeros(100, dtype=np.float32)
    result = manager.finalize(dummy_audio)
    # No additional STT call for the short final chunk
    assert mock_stt.transcribe.call_count == calls_before
    assert result == "chunk text"
