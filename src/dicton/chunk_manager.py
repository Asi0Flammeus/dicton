"""ChunkManager — chunked STT pipeline for long recordings.

Splits audio into overlapping chunks at silence boundaries and dispatches
them concurrently to the STT provider. Results are concatenated in order.
"""

import io
import logging
import wave
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass

import numpy as np

from .stt_provider import STTProvider

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChunkConfig:
    enabled: bool
    threshold_s: float
    silence_threshold: float
    silence_window_s: float
    lookback_s: float
    chunk_size: int
    sample_rate: int
    stt_timeout: float

    @classmethod
    def from_app_config(cls, cfg) -> "ChunkConfig":
        return cls(
            enabled=cfg.CHUNK_ENABLED,
            threshold_s=cfg.CHUNK_THRESHOLD_S,
            silence_threshold=cfg.CHUNK_SILENCE_THRESHOLD,
            silence_window_s=cfg.CHUNK_SILENCE_WINDOW_S,
            lookback_s=cfg.CHUNK_LOOKBACK_S,
            chunk_size=cfg.CHUNK_SIZE,
            sample_rate=cfg.SAMPLE_RATE,
            stt_timeout=cfg.STT_TIMEOUT,
        )


class ChunkManager:
    """Manages chunked parallel transcription for long recordings."""

    def __init__(self, stt_provider: STTProvider, config: ChunkConfig) -> None:
        self._stt = stt_provider
        self._config = config
        self._executor = ThreadPoolExecutor(max_workers=3)
        self._frames: list[bytes] = []
        self._chunk_boundary: int = 0
        self._futures: list[Future] = []
        self._cancelled: bool = False

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    def start_session(self) -> None:
        """Reset all session state for a new recording."""
        self._frames = []
        self._chunk_boundary = 0
        self._futures = []
        self._cancelled = False

    # ------------------------------------------------------------------
    # Recording feed
    # ------------------------------------------------------------------

    def feed_chunk(self, raw_audio: bytes) -> None:
        """Append a raw audio frame and dispatch a chunk if threshold reached."""
        self._frames.append(raw_audio)
        unchunked_frames = len(self._frames) - self._chunk_boundary
        duration_s = unchunked_frames * self._config.chunk_size / self._config.sample_rate
        if duration_s >= self._config.threshold_s:
            self._dispatch_chunk()

    # ------------------------------------------------------------------
    # Internal chunk dispatch
    # ------------------------------------------------------------------

    def _dispatch_chunk(self) -> None:
        """Find a silence cut point and submit a transcription future."""
        start_idx = self._chunk_boundary
        end_idx = len(self._frames)
        cut_point = self._find_silence_point(start_idx, end_idx)
        if cut_point is None:
            frames_per_threshold = int(
                self._config.threshold_s * self._config.sample_rate / self._config.chunk_size
            )
            cut_point = start_idx + frames_per_threshold

        frames_slice = self._frames[start_idx:cut_point]
        future = self._executor.submit(self._transcribe_chunk, frames_slice)
        self._futures.append(future)
        self._chunk_boundary = cut_point

    def _find_silence_point(self, start_idx: int, end_idx: int) -> int | None:
        """Scan backwards from end_idx for N consecutive silent frames."""
        cfg = self._config
        frames_per_window = int(cfg.silence_window_s / (cfg.chunk_size / cfg.sample_rate))
        if frames_per_window < 1:
            frames_per_window = 1

        # Scan backwards; need `frames_per_window` consecutive silent frames
        silent_run = 0
        for idx in range(end_idx - 1, start_idx - 1, -1):
            rms = self._compute_rms(self._frames[idx])
            if rms < cfg.silence_threshold:
                silent_run += 1
                if silent_run >= frames_per_window:
                    # Return the frame index where silence begins
                    return idx
            else:
                silent_run = 0
        return None

    # ------------------------------------------------------------------
    # Audio helpers
    # ------------------------------------------------------------------

    def _compute_rms(self, raw_audio: bytes) -> float:
        """Compute normalised RMS identical to the visualizer formula."""
        data = np.frombuffer(raw_audio, dtype=np.int16).astype(np.float32)
        return float(np.sqrt(np.mean(data**2)) / 8000)

    def _transcribe_chunk(self, frames: list[bytes]) -> str | None:
        """Join frames, convert to WAV, transcribe, return text or None."""
        if self._cancelled:
            return None
        raw = b"".join(frames)
        audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        wav_bytes = self._audio_to_wav(audio)
        try:
            result = self._stt.transcribe(wav_bytes)
            return result.text if result else None
        except Exception:
            logger.exception("Chunk transcription failed")
            return None

    def _audio_to_wav(self, audio: np.ndarray) -> bytes:
        """Convert float32 audio array to 16-bit mono WAV bytes."""
        pcm = (audio * 32767).astype(np.int16)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self._config.sample_rate)
            wf.writeframes(pcm.tobytes())
        return buf.getvalue()

    # ------------------------------------------------------------------
    # Properties / control
    # ------------------------------------------------------------------

    @property
    def has_chunks(self) -> bool:
        return len(self._futures) > 0

    def cancel(self) -> None:
        """Signal cancellation and attempt to cancel pending futures."""
        self._cancelled = True
        for f in self._futures:
            f.cancel()

    # ------------------------------------------------------------------
    # Finalise
    # ------------------------------------------------------------------

    def finalize(self, full_audio: np.ndarray) -> str | None:  # noqa: ARG002
        """Transcribe remaining audio, wait for all futures, return joined text."""
        if self._cancelled:
            return None

        remaining_frames = self._frames[self._chunk_boundary :]
        remaining_duration = (
            len(remaining_frames) * self._config.chunk_size / self._config.sample_rate
        )

        final_future: Future | None = None
        if remaining_frames and remaining_duration > 0.5:
            final_future = self._executor.submit(self._transcribe_chunk, remaining_frames)

        results: list[str] = []
        for f in self._futures:
            try:
                text = f.result(timeout=self._config.stt_timeout)
                if text:
                    results.append(text)
            except Exception:
                logger.exception("Error retrieving chunk result")

        if final_future is not None:
            try:
                text = final_future.result(timeout=self._config.stt_timeout)
                if text:
                    results.append(text)
            except Exception:
                logger.exception("Error retrieving final chunk result")

        if not results:
            return None
        return " ".join(results)
