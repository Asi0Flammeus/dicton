"""Mistral Voxtral STT Provider for Dicton

Provides batch transcription using Mistral's Voxtral model.
Offers 85% cost savings vs ElevenLabs with comparable accuracy.

Key constraints:
- Batch-only (no streaming)
- ~15 minute max duration per request
- Cannot use language hint + timestamps together
"""

import hashlib
import logging
import threading
import time
import wave
from collections.abc import Callable, Iterator

from .provider import (
    STTCapability,
    STTProvider,
    STTProviderConfig,
    TranscriptionResult,
    WordInfo,
)

logger = logging.getLogger(__name__)


# Number of warm sockets we keep parked in the httpx pool. Coupled with
# chunk_manager.max_workers — bumping that to 2 should be paired with bumping
# this constant. See reduce-latency.md §3.
_PREWARM_POOL_SIZE = 2
_KEEPALIVE_EXPIRY_S = 300.0
_MISTRAL_BASE_URL = "https://api.mistral.ai"


class MistralSTTProvider(STTProvider):
    """Mistral Voxtral batch transcription provider.

    Features:
    - Batch transcription via REST API
    - Word-level timestamps (when not using language hint)
    - Auto language detection
    - ~20x real-time processing speed

    Costs ~$0.001/min ($0.06/hr) vs $0.40/hr for ElevenLabs.
    """

    # Pinned in code; MISTRAL_STT_MODEL env var is intentionally ignored.
    # voxtral-mini-2602 = Mini Transcribe V2 (Feb 2026). Note: voxtral-mini-latest
    # still aliases to 2507, so the date suffix must be hard-coded to get V2.
    DEFAULT_MODEL = "voxtral-mini-2602"

    def __init__(self, config: STTProviderConfig | None = None, *, debug: bool = False):
        """Initialize Mistral provider.

        Args:
            config: Provider configuration. If None, uses environment defaults.
            debug: Enable debug logging to stdout.
        """
        super().__init__(config)
        self._client = None
        self._http_client = None  # httpx.Client backing the SDK; pooled.
        self._api_key_hash: str | None = None
        self._is_available = False
        self._debug = debug

        self._config.model = self.DEFAULT_MODEL

        # Get API key from config or environment
        if not self._config.api_key:
            import os

            self._config.api_key = os.getenv("MISTRAL_API_KEY", "")

        # Get timeout from config or environment
        if self._config.timeout == 30.0:  # Default value
            import os

            self._config.timeout = float(os.getenv("STT_TIMEOUT", "120"))

    @property
    def name(self) -> str:
        return "Mistral Voxtral"

    @property
    def capabilities(self) -> set[STTCapability]:
        return {STTCapability.BATCH, STTCapability.WORD_TIMESTAMPS}

    @property
    def max_audio_duration(self) -> int | None:
        """Maximum audio duration: 30 minutes (1800 seconds)."""
        return 1800

    @property
    def max_audio_size(self) -> int | None:
        """Maximum audio size: 100 MB."""
        return 100_000_000

    def _compute_api_key_hash(self) -> str:
        """Compute hash of current API key for change detection."""
        return hashlib.sha256(self._config.api_key.encode()).hexdigest()[:16]

    def is_available(self) -> bool:
        """Check if Mistral is available and configured.

        Re-checks availability when API key changes.

        Returns:
            True if API key is set and client can be initialized.
        """
        if not self._config.api_key:
            logger.debug("Mistral API key not configured")
            self._is_available = False
            self._api_key_hash = None
            return False

        # Check if API key changed
        current_hash = self._compute_api_key_hash()
        if self._api_key_hash == current_hash and self._client is not None:
            return self._is_available

        # API key changed or first check - reinitialize client
        self._api_key_hash = current_hash
        self._close_http_client()
        self._client = None

        try:
            try:
                from mistralai import Mistral
            except ImportError:
                from mistralai.client import Mistral

            self._http_client = self._build_http_client()
            kwargs = {
                "api_key": self._config.api_key,
                "timeout_ms": int(self._config.timeout * 1000),
            }
            if self._http_client is not None:
                kwargs["client"] = self._http_client
            self._client = Mistral(**kwargs)
            self._is_available = True
            return True
        except ImportError:
            logger.warning("mistralai package not installed")
            self._is_available = False
            return False
        except Exception as e:
            logger.error(f"Failed to initialize Mistral client: {e}")
            self._is_available = False
            return False

    def _build_http_client(self):
        """Create a pooled httpx.Client for the Mistral SDK.

        Returns ``None`` if httpx is unavailable; the SDK then falls back to
        its own internal client (no pooling, but functional).
        """
        try:
            import httpx
        except ImportError:
            return None
        limits = httpx.Limits(
            max_keepalive_connections=_PREWARM_POOL_SIZE,
            max_connections=_PREWARM_POOL_SIZE * 2,
            keepalive_expiry=_KEEPALIVE_EXPIRY_S,
        )
        timeout = httpx.Timeout(self._config.timeout)
        return httpx.Client(limits=limits, timeout=timeout)

    def _close_http_client(self) -> None:
        if self._http_client is not None:
            try:
                self._http_client.close()
            except Exception:
                pass
            self._http_client = None

    def prewarm(self, n: int = _PREWARM_POOL_SIZE) -> None:
        """Best-effort: open ``n`` warm sockets to the Mistral API.

        Spawns daemon threads that issue cheap GETs against the API base URL
        through the pooled httpx client. The transcribe call moments later
        reuses these sockets and skips the TCP+TLS handshake. Silent on any
        error; the daemon must keep running.
        """
        if self._http_client is None or n <= 0:
            return

        def _warm_one() -> None:
            try:
                # GET / — Mistral returns a 401/404, but the TLS handshake
                # is what we're after; keepalive parks the socket in the pool.
                self._http_client.get(_MISTRAL_BASE_URL + "/", timeout=5.0)
            except Exception as exc:
                logger.debug("mistral prewarm failed: %s", exc)

        for _ in range(n):
            threading.Thread(target=_warm_one, daemon=True).start()

    def _ensure_client(self) -> bool:
        """Ensure client is initialized with current API key.

        Returns:
            True if client is ready.
        """
        # Check if API key changed since last initialization
        if self._client is not None and self._api_key_hash == self._compute_api_key_hash():
            return True

        # Reinitialize via is_available() which handles key change detection
        return self.is_available()

    _MAX_RETRIES = 3
    _RETRY_BASE_DELAY = 2.0  # seconds, doubles each attempt

    @staticmethod
    def _is_retryable(exc: Exception) -> bool:
        """Check if an API error is transient and worth retrying."""
        msg = str(exc)
        return "429" in msg or "capacity_exceeded" in msg or "rate_limit" in msg

    def transcribe(
        self, audio_data: bytes, *, _raise_on_retryable: bool = False
    ) -> TranscriptionResult | None:
        """Transcribe audio data using Mistral Voxtral.

        Args:
            audio_data: Audio data as bytes (WAV or raw PCM int16).
            _raise_on_retryable: If True, raise retryable errors instead of
                retrying internally.  Used by ChunkManager so its own retry
                loop can handle backoff.

        Returns:
            TranscriptionResult on success, None on failure.
        """
        if not audio_data:
            return None

        if not self._validate_audio(audio_data):
            return None

        if not self._ensure_client():
            logger.error("Mistral client not available")
            return None

        # Convert to WAV format
        wav_buffer = self._convert_to_wav(audio_data)
        if wav_buffer is None:
            return None

        wav_content = wav_buffer.read()

        if self._debug:
            print(
                f"[Mistral] Calling API: model={self._config.model}, audio={len(wav_content)} bytes"
            )

        last_exc: Exception | None = None
        max_attempts = 1 if _raise_on_retryable else self._MAX_RETRIES

        for attempt in range(1, max_attempts + 1):
            try:
                # Call Mistral API
                # Note: Cannot use language + timestamp_granularities together
                result = self._client.audio.transcriptions.complete(
                    model=self._config.model,
                    file={"content": wav_content, "file_name": "audio.wav"},
                )

                if self._debug:
                    chars = len(result.text) if result and hasattr(result, "text") else 0
                    print(f"[Mistral] Response received: {chars} chars")

                if not result or not hasattr(result, "text"):
                    logger.warning("Mistral returned no text")
                    return None

                # Build result
                transcription = TranscriptionResult(
                    text=result.text or "",
                    language=getattr(result, "language", "") or "",
                    is_final=True,
                )

                # Extract word timestamps if available
                if hasattr(result, "words") and result.words:
                    transcription.words = [
                        WordInfo(
                            word=w.word,
                            start=w.start,
                            end=w.end,
                            confidence=getattr(w, "confidence", 1.0),
                        )
                        for w in result.words
                    ]

                # Calculate duration from audio
                wav_buffer.seek(0)
                try:
                    with wave.open(wav_buffer, "rb") as wav:
                        frames = wav.getnframes()
                        rate = wav.getframerate()
                        transcription.duration = frames / rate
                except Exception as e:
                    logger.debug(f"Could not calculate audio duration: {e}")

                return transcription

            except Exception as e:
                last_exc = e
                if self._is_retryable(e):
                    if _raise_on_retryable:
                        raise
                    if attempt < max_attempts:
                        delay = self._RETRY_BASE_DELAY * (2 ** (attempt - 1))
                        logger.warning(
                            "Mistral 429 — retrying in %.0fs (attempt %d/%d)",
                            delay,
                            attempt,
                            max_attempts,
                        )
                        time.sleep(delay)
                        continue
                # Non-retryable or exhausted retries
                break

        logger.error("Mistral transcription failed: %s", last_exc)
        return None

    def stream_transcribe(
        self,
        audio_generator: Iterator[bytes],
        on_partial: Callable[[TranscriptionResult], None] | None = None,
    ) -> TranscriptionResult | None:
        """Transcribe audio stream (falls back to batch mode).

        Mistral doesn't support streaming, so we collect all chunks
        and transcribe in batch.

        Args:
            audio_generator: Iterator yielding audio chunks.
            on_partial: Optional callback (not used for Mistral).

        Returns:
            Final TranscriptionResult on success, None on failure.
        """
        # Collect all audio chunks
        chunks = list(audio_generator)
        if not chunks:
            return None

        audio_data = b"".join(chunks)
        return self.transcribe(audio_data)

    def translate(
        self, audio_data: bytes, target_language: str = "en"
    ) -> TranscriptionResult | None:
        """Translate audio (not supported by Mistral).

        Mistral Voxtral doesn't have native translation.

        Args:
            audio_data: Audio data as bytes.
            target_language: Target language code.

        Returns:
            None (translation not supported).
        """
        # Mistral doesn't support native translation
        return None
