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


class MistralSTTProvider(STTProvider):
    """Mistral Voxtral batch transcription provider.

    Features:
    - Batch transcription via REST API
    - Word-level timestamps (when not using language hint)
    - Auto language detection
    - ~20x real-time processing speed

    Costs ~$0.001/min ($0.06/hr) vs $0.40/hr for ElevenLabs.
    """

    DEFAULT_MODEL = "voxtral-mini-latest"

    def __init__(self, config: STTProviderConfig | None = None):
        """Initialize Mistral provider.

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

            self._config.model = os.getenv("MISTRAL_STT_MODEL", self.DEFAULT_MODEL)

        # Get API key from config or environment
        if not self._config.api_key:
            import os

            self._config.api_key = os.getenv("MISTRAL_API_KEY", "")

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
        self._client = None

        try:
            from mistralai import Mistral

            self._client = Mistral(api_key=self._config.api_key)
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
        """Transcribe audio data using Mistral Voxtral.

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
            logger.error("Mistral client not available")
            return None

        # Convert to WAV format
        wav_buffer = self._convert_to_wav(audio_data)
        if wav_buffer is None:
            return None

        try:
            # Debug output for verification
            from .config import config as app_config

            if app_config.DEBUG:
                wav_buffer.seek(0, 2)  # Seek to end
                audio_size = wav_buffer.tell()
                wav_buffer.seek(0)  # Reset
                print(f"[Mistral] 🔄 Calling API: model={self._config.model}, audio={audio_size} bytes")

            # Call Mistral API
            # Note: Cannot use language + timestamp_granularities together
            result = self._client.audio.transcriptions.complete(
                model=self._config.model,
                file={"content": wav_buffer.read(), "file_name": "audio.wav"},
            )

            if app_config.DEBUG:
                print(f"[Mistral] ✓ Response received: {len(result.text) if result and hasattr(result, 'text') else 0} chars")

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
            logger.error(f"Mistral transcription failed: {e}")
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
