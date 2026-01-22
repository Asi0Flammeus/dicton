"""ElevenLabs Scribe STT Provider for Dicton

Provides batch transcription using ElevenLabs' Scribe model.
High-accuracy transcription with word-level timestamps.

Key features:
- Batch-only (no streaming)
- Word-level timestamps
- Auto language detection
"""

import hashlib
import logging
import wave
from collections.abc import Callable, Iterator

from .stt_provider import (
    STTCapability,
    STTProvider,
    STTProviderConfig,
    TranscriptionResult,
    WordInfo,
)

logger = logging.getLogger(__name__)


class ElevenLabsSTTProvider(STTProvider):
    """ElevenLabs Scribe batch transcription provider.

    Features:
    - Batch transcription via REST API
    - Word-level timestamps
    - Auto language detection
    - High accuracy for multiple languages
    """

    DEFAULT_MODEL = "scribe_v1"

    def __init__(self, config: STTProviderConfig | None = None):
        """Initialize ElevenLabs provider.

        Args:
            config: Provider configuration. If None, uses environment defaults.
        """
        super().__init__(config)
        self._client = None
        self._api_key_hash: str | None = None
        self._is_available = False

        # Use config model or fall back to environment/default
        if not self._config.model:
            import os

            self._config.model = os.getenv("ELEVENLABS_MODEL", self.DEFAULT_MODEL)

        # Get API key from config or environment
        if not self._config.api_key:
            import os

            self._config.api_key = os.getenv("ELEVENLABS_API_KEY", "")

        # Get timeout from config or environment
        if self._config.timeout == 30.0:  # Default value
            import os

            self._config.timeout = float(os.getenv("STT_TIMEOUT", "120"))

    @property
    def name(self) -> str:
        return "ElevenLabs Scribe"

    @property
    def capabilities(self) -> set[STTCapability]:
        return {STTCapability.BATCH, STTCapability.WORD_TIMESTAMPS}

    @property
    def max_audio_size(self) -> int | None:
        """Maximum audio size: 3 GB (ElevenLabs limit)."""
        return 3_000_000_000

    def _compute_api_key_hash(self) -> str:
        """Compute hash of current API key for change detection."""
        return hashlib.sha256(self._config.api_key.encode()).hexdigest()[:16]

    def is_available(self) -> bool:
        """Check if ElevenLabs is available and configured.

        Re-checks availability when API key changes.

        Returns:
            True if API key is set and client can be initialized.
        """
        if not self._config.api_key:
            logger.debug("ElevenLabs API key not configured")
            self._is_available = False
            self._api_key_hash = None
            return False

        # Check if API key changed
        current_hash = self._compute_api_key_hash()
        if self._api_key_hash == current_hash and self._client is not None:
            return self._is_available

        # API key changed or first check - reinitialize client
        self._api_key_hash = current_hash
        self._client = None

        try:
            from elevenlabs.client import ElevenLabs

            self._client = ElevenLabs(
                api_key=self._config.api_key, timeout=self._config.timeout
            )
            self._is_available = True
            return True
        except ImportError:
            logger.warning("elevenlabs package not installed")
            self._is_available = False
            return False
        except Exception as e:
            logger.error(f"Failed to initialize ElevenLabs client: {e}")
            self._is_available = False
            return False

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

    def transcribe(self, audio_data: bytes) -> TranscriptionResult | None:
        """Transcribe audio data using ElevenLabs Scribe.

        Args:
            audio_data: Audio data as bytes (WAV or raw PCM int16).

        Returns:
            TranscriptionResult on success, None on failure.
        """
        if not audio_data:
            return None

        if not self._validate_audio(audio_data):
            return None

        if not self._ensure_client():
            logger.error("ElevenLabs client not available")
            return None

        # Convert to WAV format
        wav_buffer = self._convert_to_wav(audio_data)
        if wav_buffer is None:
            return None

        try:
            # Call ElevenLabs STT API (language_code=None for auto-detect)
            result = self._client.speech_to_text.convert(
                file=wav_buffer,
                model_id=self._config.model,
            )

            if not result or not hasattr(result, "text"):
                logger.warning("ElevenLabs returned no text")
                return None

            # Build result
            transcription = TranscriptionResult(
                text=result.text or "",
                language=getattr(result, "language_code", "") or "",
                is_final=True,
            )

            # Extract word timestamps if available
            if hasattr(result, "words") and result.words:
                transcription.words = [
                    WordInfo(
                        word=w.text if hasattr(w, "text") else str(w),
                        start=getattr(w, "start", 0.0),
                        end=getattr(w, "end", 0.0),
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
            logger.error(f"ElevenLabs transcription failed: {e}")
            return None

    def stream_transcribe(
        self,
        audio_generator: Iterator[bytes],
        on_partial: Callable[[TranscriptionResult], None] | None = None,
    ) -> TranscriptionResult | None:
        """Transcribe audio stream (falls back to batch mode).

        ElevenLabs Scribe doesn't support streaming, so we collect all chunks
        and transcribe in batch.

        Args:
            audio_generator: Iterator yielding audio chunks.
            on_partial: Optional callback (not used for ElevenLabs).

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
        """Translate audio (not supported by ElevenLabs Scribe).

        ElevenLabs Scribe doesn't have native translation.

        Args:
            audio_data: Audio data as bytes.
            target_language: Target language code.

        Returns:
            None (translation not supported).
        """
        # ElevenLabs Scribe doesn't support native translation
        return None
