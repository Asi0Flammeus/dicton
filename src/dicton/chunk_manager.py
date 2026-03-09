"""ChunkManager — chunked STT pipeline for long recordings.

Splits audio into overlapping chunks at silence boundaries and dispatches
them concurrently to the STT provider. Results are concatenated in order.
"""

import io
import logging
import time
import wave
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass

import numpy as np

from .stt_provider import STTProvider

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChunkConfig:
    enabled: bool
    min_chunk_s: float
    max_chunk_s: float
    overlap_s: float
    silence_threshold: float
    silence_window_s: float
    chunk_size: int
    sample_rate: int
    stt_timeout: float

    @classmethod
    def from_app_config(cls, cfg) -> "ChunkConfig":
        return cls(
            enabled=cfg.CHUNK_ENABLED,
            min_chunk_s=cfg.CHUNK_MIN_S,
            max_chunk_s=cfg.CHUNK_MAX_S,
            overlap_s=cfg.CHUNK_OVERLAP_S,
            silence_threshold=cfg.CHUNK_SILENCE_THRESHOLD,
            silence_window_s=cfg.CHUNK_SILENCE_WINDOW_S,
            chunk_size=cfg.CHUNK_SIZE,
            sample_rate=cfg.SAMPLE_RATE,
            stt_timeout=cfg.STT_TIMEOUT,
        )


@dataclass
class FinalizeResult:
    text: str | None
    total_chunks: int
    failed_chunks: int
    is_partial: bool  # failed_chunks > 0 and text is not None


class ChunkManager:
    """Manages chunked parallel transcription for long recordings."""

    def __init__(self, stt_provider: STTProvider, config: ChunkConfig) -> None:
        self._stt = stt_provider
        self._config = config
        self._executor = ThreadPoolExecutor(max_workers=3)

        # Precompute frame-related constants
        self._frame_duration = config.chunk_size / config.sample_rate
        self._frames_per_window = max(1, int(config.silence_window_s / self._frame_duration))
        self._overlap_frames = int(config.overlap_s / self._frame_duration)

        # Session state
        self._frames: list[bytes] = []
        self._chunk_boundary: int = 0
        self._futures: list[Future] = []
        self._cancelled: bool = False
        self._silent_run: int = 0

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    def start_session(self) -> None:
        """Reset all session state for a new recording."""
        self._frames = []
        self._chunk_boundary = 0
        self._futures = []
        self._cancelled = False
        self._silent_run = 0

    # ------------------------------------------------------------------
    # Recording feed
    # ------------------------------------------------------------------

    def feed_chunk(self, raw_audio: bytes) -> None:
        """Append a raw audio frame and dispatch a chunk on silence or hard cut."""
        self._frames.append(raw_audio)

        rms = self._compute_rms(raw_audio)
        if rms < self._config.silence_threshold:
            self._silent_run += 1
        else:
            self._silent_run = 0

        unchunked_frames = len(self._frames) - self._chunk_boundary
        duration_s = unchunked_frames * self._frame_duration

        if self._silent_run >= self._frames_per_window and duration_s >= self._config.min_chunk_s:
            # Cut at the start of the silence run
            cut_point = len(self._frames) - self._silent_run
            self._dispatch_chunk(cut_point, "silence")
        elif duration_s >= self._config.max_chunk_s:
            self._dispatch_chunk(len(self._frames), "hard")

    # ------------------------------------------------------------------
    # Internal chunk dispatch
    # ------------------------------------------------------------------

    def _dispatch_chunk(self, cut_point: int, cut_type: str) -> None:
        """Extract frames up to cut_point and submit a transcription future."""
        frames_slice = self._frames[self._chunk_boundary : cut_point]
        chunk_idx = len(self._futures)
        duration_s = len(frames_slice) * self._frame_duration

        future = self._executor.submit(self._transcribe_chunk, frames_slice, chunk_idx)
        self._futures.append(future)

        # Overlap: rewind boundary so next chunk re-includes trailing context
        self._chunk_boundary = max(cut_point - self._overlap_frames, self._chunk_boundary)
        self._silent_run = 0

        logger.info("Dispatched chunk %d: %.1fs, cut=%s", chunk_idx, duration_s, cut_type)

    # ------------------------------------------------------------------
    # Audio helpers
    # ------------------------------------------------------------------

    def _compute_rms(self, raw_audio: bytes) -> float:
        """Compute normalised RMS identical to the visualizer formula."""
        data = np.frombuffer(raw_audio, dtype=np.int16).astype(np.float32)
        return float(np.sqrt(np.mean(data**2)) / 8000)

    def _transcribe_chunk(self, frames: list[bytes], chunk_idx: int) -> str | None:
        """Join frames, convert to WAV, transcribe with retry, return text or None."""
        if self._cancelled:
            return None
        raw = b"".join(frames)
        audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        wav_bytes = self._audio_to_wav(audio)

        max_attempts = 2
        for attempt in range(1, max_attempts + 1):
            t0 = time.monotonic()
            try:
                result = self._stt.transcribe(wav_bytes)
                latency = time.monotonic() - t0
                text = result.text if result else None
                logger.info(
                    "Chunk %d transcribed: %.2fs latency, %d chars",
                    chunk_idx,
                    latency,
                    len(text) if text else 0,
                )
                return text
            except Exception:
                latency = time.monotonic() - t0
                logger.warning(
                    "Chunk %d attempt %d/%d failed (%.2fs)",
                    chunk_idx,
                    attempt,
                    max_attempts,
                    latency,
                )
                if attempt < max_attempts:
                    time.sleep(1)

        logger.error("Chunk %d: all %d attempts exhausted", chunk_idx, max_attempts)
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

    def finalize(self) -> FinalizeResult:
        """Transcribe remaining audio, wait for all futures, return FinalizeResult."""
        if self._cancelled:
            return FinalizeResult(
                text=None,
                total_chunks=len(self._futures),
                failed_chunks=0,
                is_partial=False,
            )

        remaining_frames = self._frames[self._chunk_boundary :]
        remaining_duration = len(remaining_frames) * self._frame_duration

        final_future: Future | None = None
        if remaining_frames and remaining_duration > 0.5:
            chunk_idx = len(self._futures)
            final_future = self._executor.submit(
                self._transcribe_chunk, remaining_frames, chunk_idx
            )

        results: list[str] = []
        failed_chunks = 0

        for f in self._futures:
            try:
                text = f.result(timeout=self._config.stt_timeout)
                if text:
                    results.append(text)
                else:
                    failed_chunks += 1
            except Exception:
                logger.exception("Error retrieving chunk result")
                failed_chunks += 1

        if final_future is not None:
            try:
                text = final_future.result(timeout=self._config.stt_timeout)
                if text:
                    results.append(text)
                else:
                    failed_chunks += 1
            except Exception:
                logger.exception("Error retrieving final chunk result")
                failed_chunks += 1

        total_chunks = len(self._futures) + (1 if final_future is not None else 0)
        total_duration = len(self._frames) * self._frame_duration
        joined = " ".join(results) if results else None

        logger.info(
            "Session summary: %.1fs total, %d chunks dispatched, %d ok, %d failed, %d chars",
            total_duration,
            total_chunks,
            total_chunks - failed_chunks,
            failed_chunks,
            len(joined) if joined else 0,
        )

        return FinalizeResult(
            text=joined,
            total_chunks=total_chunks,
            failed_chunks=failed_chunks,
            is_partial=failed_chunks > 0 and joined is not None,
        )
