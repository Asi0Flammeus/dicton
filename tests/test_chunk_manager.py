"""Unit tests for src.dicton.chunk_manager."""

import os
import threading
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from dicton.adapters.audio.chunk_manager import ChunkConfig, ChunkManager, FinalizeResult
from dicton.adapters.stt.provider import TranscriptionResult

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
CHUNK_SIZE = 1024
SAMPLE_RATE = 16000
BYTES_PER_FRAME = CHUNK_SIZE * 2  # int16 = 2 bytes per sample
SILENCE_FRAME = b"\x00" * BYTES_PER_FRAME

# Frame math:
# frame_duration = 1024 / 16000 = 0.064s
# min_chunk_s=2.0 → 32 frames (2.048s)
# max_chunk_s=8.0 → 125 frames (8.0s)
# silence_window_s=0.3 → frames_per_window = int(0.3/0.064) = 4
# overlap_s=0.5 → overlap_frames = int(0.5/0.064) = 7


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
        min_chunk_s=2.0,
        max_chunk_s=8.0,
        overlap_s=0.5,
        silence_threshold=0.03,
        silence_window_s=0.3,
        chunk_size=CHUNK_SIZE,
        sample_rate=SAMPLE_RATE,
        stt_timeout=120.0,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_short_recording_no_chunks(mock_stt, chunk_config):
    """Audio shorter than min_chunk_s does not dispatch any chunks."""
    manager = ChunkManager(mock_stt, chunk_config)
    manager.start_session()
    # 20 frames × 0.064s = 1.28s < 2.0s min
    for _ in range(20):
        manager.feed_chunk(SILENCE_FRAME)
    assert not manager.has_chunks
    mock_stt.transcribe.assert_not_called()


def test_silence_cut_after_min(mock_stt, chunk_config):
    """Speech > min_chunk_s then silence >= silence_window triggers dispatch."""
    manager = ChunkManager(mock_stt, chunk_config)
    manager.start_session()
    # 35 speech frames = 2.24s > 2.0s min, then 5 silence frames (>= 4 window)
    for _ in range(35):
        manager.feed_chunk(_speech_frame())
    for _ in range(5):
        manager.feed_chunk(SILENCE_FRAME)
    assert manager.has_chunks
    for f in manager._futures:
        f.result(timeout=5.0)
    assert mock_stt.transcribe.call_count == 1


def test_hard_cut_at_max(mock_stt, chunk_config):
    """Continuous speech past max_chunk_s triggers hard cut dispatch."""
    manager = ChunkManager(mock_stt, chunk_config)
    manager.start_session()
    # 126 speech frames = 8.064s > 8.0s max → hard cut
    for _ in range(126):
        manager.feed_chunk(_speech_frame())
    assert manager.has_chunks
    for f in manager._futures:
        f.result(timeout=5.0)
    assert mock_stt.transcribe.call_count == 1


def test_overlap_boundary(mock_stt, chunk_config):
    """After silence dispatch, _chunk_boundary == cut_point - overlap_frames."""
    manager = ChunkManager(mock_stt, chunk_config)
    manager.start_session()
    for _ in range(35):
        manager.feed_chunk(_speech_frame())
    for _ in range(5):
        manager.feed_chunk(SILENCE_FRAME)
    assert manager.has_chunks
    for f in manager._futures:
        f.result(timeout=5.0)
    # Infer cut_point from WAV data sent to STT
    wav_bytes = mock_stt.transcribe.call_args[0][0]
    wav_audio_bytes = len(wav_bytes) - 44  # WAV header = 44 bytes
    frames_sent = wav_audio_bytes // BYTES_PER_FRAME
    overlap_frames = int(
        chunk_config.overlap_s / (chunk_config.chunk_size / chunk_config.sample_rate)
    )
    assert overlap_frames == 7
    # First dispatch starts at boundary 0, so cut_point == frames_sent
    assert manager._chunk_boundary == frames_sent - overlap_frames


@patch("dicton.adapters.audio.chunk_manager.time.sleep")
def test_retry_on_failure(mock_sleep, mock_stt, chunk_config):
    """_transcribe_chunk retries on transient error; recovered text present in result."""
    call_count = [0]

    def side_effect(_audio, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            raise RuntimeError("temporary failure")
        return TranscriptionResult(text="recovered text")

    mock_stt.transcribe.side_effect = side_effect
    manager = ChunkManager(mock_stt, chunk_config)
    manager.start_session()
    # Hard cut at 125 frames (8.0 s >= max); remaining overlap = 7 = 0.448 s < 0.5 s
    for _ in range(125):
        manager.feed_chunk(_speech_frame())
    assert manager.has_chunks
    result = manager.finalize()
    assert result.text is not None
    assert "recovered" in result.text
    # 2 calls: first raised, second succeeded
    assert mock_stt.transcribe.call_count == 2
    mock_sleep.assert_called_once_with(2.0)


def test_finalize_returns_result(mock_stt, chunk_config):
    """finalize returns FinalizeResult with correct text, counts, and is_partial."""
    manager = ChunkManager(mock_stt, chunk_config)
    manager.start_session()
    # Hard cut at 125 + enough remaining for finalize (> 0.5 s)
    # 140 frames: boundary = 118, remaining = 22 = 1.408 s → finalize sends
    for _ in range(140):
        manager.feed_chunk(_speech_frame())
    assert manager.has_chunks
    result = manager.finalize()
    assert isinstance(result, FinalizeResult)
    assert result.text is not None
    assert "chunk text" in result.text
    assert result.total_chunks == 2  # 1 dispatch + 1 finalize
    assert result.failed_chunks == 0
    assert result.is_partial is False


def test_rms_computation(mock_stt, chunk_config):
    """_compute_rms returns expected values for silence and known amplitudes.

    RMS is AC-coupled (DC offset removed), so constant signals yield 0
    and only the varying component is measured.
    """
    manager = ChunkManager(mock_stt, chunk_config)
    # Silence: all zeros → RMS = 0
    assert manager._compute_rms(SILENCE_FRAME) == 0.0
    # Constant value (pure DC) → RMS = 0 after DC removal
    max_val = np.full(CHUNK_SIZE, 32767, dtype=np.int16).tobytes()
    assert manager._compute_rms(max_val) == 0.0
    # Alternating +/- signal (zero mean, pure AC) → RMS = amplitude / 8000
    alt = np.array([10000, -10000] * (CHUNK_SIZE // 2), dtype=np.int16).tobytes()
    assert abs(manager._compute_rms(alt) - 10000.0 / 8000.0) < 1e-4
    # DC offset + AC signal: only AC component measured
    biased = np.array([20000, 0] * (CHUNK_SIZE // 2), dtype=np.int16).tobytes()
    assert abs(manager._compute_rms(biased) - 10000.0 / 8000.0) < 1e-4


def test_cancel_discards_all(mock_stt, chunk_config):
    """After cancel(), finalize() returns FinalizeResult with text=None."""
    manager = ChunkManager(mock_stt, chunk_config)
    manager.start_session()
    for _ in range(126):
        manager.feed_chunk(_speech_frame())
    assert manager.has_chunks
    manager.cancel()
    result = manager.finalize()
    assert isinstance(result, FinalizeResult)
    assert result.text is None


def test_start_session_resets_state(mock_stt, chunk_config):
    """start_session() fully resets internal state between recordings."""
    manager = ChunkManager(mock_stt, chunk_config)
    manager.start_session()
    for _ in range(126):
        manager.feed_chunk(_speech_frame())
    manager.finalize()
    manager.start_session()
    assert manager._frames == []
    assert manager._futures == []
    assert manager._chunk_boundary == 0
    assert manager._silent_run == 0
    assert not manager.has_chunks


@patch("dicton.adapters.audio.chunk_manager.time.sleep")
def test_provider_error_partial_results(_mock_sleep, mock_stt, chunk_config):
    """One chunk fails all retries -> is_partial=True, failed_chunks=1."""
    call_count = [0]
    lock = threading.Lock()

    def side_effect(_audio, **kwargs):
        with lock:
            n = call_count[0]
            call_count[0] += 1
        # Chunk 0 (dispatch 1): call 0 -> succeed
        # Chunk 1 (dispatch 2): calls 1,2,3 -> all fail (3 retries exhausted)
        # Chunk 2 (finalize):   call 4 -> succeed
        if n in (1, 2, 3):
            raise RuntimeError("STT provider failure")
        return TranscriptionResult(text=f"text{n}")

    mock_stt.transcribe.side_effect = side_effect
    manager = ChunkManager(mock_stt, chunk_config)
    manager.start_session()
    # 260 speech frames -> 2 hard-cut dispatches + finalize remaining > 0.5 s
    for _ in range(260):
        manager.feed_chunk(_speech_frame())
    result = manager.finalize()
    assert isinstance(result, FinalizeResult)
    assert result.is_partial is True
    assert result.failed_chunks == 1
    assert result.text is not None


def test_short_final_chunk_skipped(mock_stt, chunk_config):
    """Remaining audio < 0.5s after the last dispatch is not sent to STT."""
    manager = ChunkManager(mock_stt, chunk_config)
    manager.start_session()
    # Hard cut at frame 125 (8.0s >= 8.0s), boundary set back to 118 (overlap=7)
    # Feed exactly 125: remaining = 125 - 118 = 7 frames = 0.448s < 0.5s
    for _ in range(125):
        manager.feed_chunk(_speech_frame())
    assert manager.has_chunks
    for f in manager._futures:
        f.result(timeout=5.0)
    calls_before = mock_stt.transcribe.call_count
    result = manager.finalize()
    # No additional STT call for the short final chunk
    assert mock_stt.transcribe.call_count == calls_before
    assert isinstance(result, FinalizeResult)
    assert result.text == "chunk text"
