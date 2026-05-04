"""Groq Whisper STT Provider for Dicton.

Provides batch transcription using Groq Cloud's hosted Whisper Large v3 Turbo,
the OpenAI-compatible STT endpoint at ``api.groq.com``. ~0.3-0.5 s wall-clock
on 10-18 s clips — markedly faster than Voxtral while remaining cheaper
($0.04/h vs $0.06/h on Mistral).

Constraints (Groq Cloud free + paid tiers, as of 2026):
- 25 MB max file size, 7200 s of audio per minute (rate).
- For our 5-30 s dictation clips the limits are not load-bearing.
"""

import hashlib
import logging
import threading
import time
import wave

from .provider import (
    STTCapability,
    STTProvider,
    STTProviderConfig,
    TranscriptionResult,
)

logger = logging.getLogger(__name__)


# Mirror Mistral's pool size — coupled with chunk_manager.max_workers.
_PREWARM_POOL_SIZE = 2
_KEEPALIVE_EXPIRY_S = 300.0
_GROQ_BASE_URL = "https://api.groq.com"


class GroqSTTProvider(STTProvider):
    """Groq Whisper Large v3 Turbo batch transcription provider."""

    # Pinned in code; GROQ_STT_MODEL env var is intentionally ignored
    # (per the hardcode-models policy in reduce-latency.md).
    DEFAULT_MODEL = "whisper-large-v3-turbo"

    def __init__(self, config: STTProviderConfig | None = None, *, debug: bool = False):
        super().__init__(config)
        self._client = None
        self._http_client = None
        self._api_key_hash: str | None = None
        self._is_available = False
        self._debug = debug

        self._config.model = self.DEFAULT_MODEL

        if not self._config.api_key:
            import os

            self._config.api_key = os.getenv("GROQ_API_KEY", "")

        if self._config.timeout == 30.0:
            import os

            self._config.timeout = float(os.getenv("STT_TIMEOUT", "120"))

    @property
    def name(self) -> str:
        return "Groq Whisper"

    @property
    def capabilities(self) -> set[STTCapability]:
        return {STTCapability.BATCH, STTCapability.WORD_TIMESTAMPS}

    @property
    def max_audio_duration(self) -> int | None:
        # Groq's per-request audio cap is well above our chunk sizes; gate on
        # file size only via max_audio_size below.
        return None

    @property
    def max_audio_size(self) -> int | None:
        """Maximum audio size: 25 MB (Groq Cloud limit)."""
        return 25_000_000

    def _compute_api_key_hash(self) -> str:
        return hashlib.sha256(self._config.api_key.encode()).hexdigest()[:16]

    def is_available(self) -> bool:
        if not self._config.api_key:
            logger.debug("Groq API key not configured")
            self._is_available = False
            self._api_key_hash = None
            return False

        current_hash = self._compute_api_key_hash()
        if self._api_key_hash == current_hash and self._client is not None:
            return self._is_available

        self._api_key_hash = current_hash
        self._close_http_client()
        self._client = None

        try:
            from groq import Groq
        except ImportError:
            logger.warning("groq package not installed")
            self._is_available = False
            return False

        try:
            self._http_client = self._build_http_client()
            kwargs = {
                "api_key": self._config.api_key,
                "timeout": self._config.timeout,
            }
            if self._http_client is not None:
                kwargs["http_client"] = self._http_client
            self._client = Groq(**kwargs)
            self._is_available = True
            return True
        except Exception as e:
            logger.error(f"Failed to initialize Groq client: {e}")
            self._is_available = False
            return False

    def _build_http_client(self):
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

    def cleanup(self) -> None:
        self._close_http_client()
        self._client = None

    def prewarm(self, n: int = _PREWARM_POOL_SIZE) -> None:
        """Open ``n`` warm sockets to the Groq API.

        The transcribe call moments later reuses these sockets and skips the
        TCP+TLS handshake. Silent on any error.
        """
        if self._http_client is None or n <= 0:
            return

        def _warm_one() -> None:
            try:
                # GET /openai/v1/ — Groq returns 401/404, but the TLS handshake
                # is what we're after; keepalive parks the socket in the pool.
                self._http_client.get(_GROQ_BASE_URL + "/openai/v1/", timeout=5.0)
            except Exception as exc:
                logger.debug("groq prewarm failed: %s", exc)

        for _ in range(n):
            threading.Thread(target=_warm_one, daemon=True).start()

    def _ensure_client(self) -> bool:
        if self._client is not None and self._api_key_hash == self._compute_api_key_hash():
            return True
        return self.is_available()

    _MAX_RETRIES = 3
    _RETRY_BASE_DELAY = 2.0

    @staticmethod
    def _is_retryable(exc: Exception) -> bool:
        msg = str(exc)
        return (
            "429" in msg or "rate_limit" in msg.lower() or "capacity" in msg.lower() or "503" in msg
        )

    def transcribe(
        self, audio_data: bytes, *, _raise_on_retryable: bool = False
    ) -> TranscriptionResult | None:
        if not audio_data:
            return None

        if not self._validate_audio(audio_data):
            return None

        if not self._ensure_client():
            logger.error("Groq client not available")
            return None

        wav_buffer = self._convert_to_wav(audio_data)
        if wav_buffer is None:
            return None

        wav_content = wav_buffer.read()

        if self._debug:
            print(f"[Groq] Calling API: model={self._config.model}, audio={len(wav_content)} bytes")

        last_exc: Exception | None = None
        max_attempts = 1 if _raise_on_retryable else self._MAX_RETRIES

        for attempt in range(1, max_attempts + 1):
            try:
                # Groq's audio.transcriptions.create expects a file tuple
                # (filename, content, content_type) like OpenAI's SDK.
                result = self._client.audio.transcriptions.create(
                    model=self._config.model,
                    file=("audio.wav", wav_content, "audio/wav"),
                )

                text = getattr(result, "text", None) or ""
                if self._debug:
                    print(f"[Groq] Response received: {len(text)} chars")

                if not text:
                    logger.warning("Groq returned no text")
                    return None

                transcription = TranscriptionResult(
                    text=text,
                    language=getattr(result, "language", "") or "",
                    is_final=True,
                )

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
                            "Groq transient error — retrying in %.0fs (attempt %d/%d): %s",
                            delay,
                            attempt,
                            max_attempts,
                            e,
                        )
                        time.sleep(delay)
                        continue
                break

        logger.error("Groq transcription failed: %s", last_exc)
        return None
