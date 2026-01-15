"""ElevenLabs STT Provider for Dicton.

Uses ElevenLabs Scribe v1/v2 model for high-quality batch transcription.
Does not support streaming - use Gladia for real-time transcription.

Documentation: https://elevenlabs.io/docs/developers/guides/cookbooks/speech-to-text/quickstart
SDK: https://github.com/elevenlabs/elevenlabs-python
"""

import io

from .stt_provider import (
    STTCapability,
    STTProvider,
    STTProviderConfig,
    TranscriptionResult,
)


class ElevenLabsSTTProvider(STTProvider):
    """ElevenLabs Speech-to-Text provider.

    Capabilities:
    - BATCH: Upload complete audio file for transcription
    - WORD_TIMESTAMPS: Per-word timing information (when available)

    Does NOT support:
    - STREAMING: ElevenLabs STT is batch-only
    - TRANSLATION: Use Gladia or LLM fallback

    Usage:
        config = STTProviderConfig(
            api_key="your_elevenlabs_key",
            model="scribe_v1",
            timeout=120.0
        )
        provider = ElevenLabsSTTProvider(config)
        result = provider.transcribe(audio_bytes)
    """

    @property
    def name(self) -> str:
        """Return provider name."""
        return "ElevenLabs"

    @property
    def capabilities(self) -> set[STTCapability]:
        """Return supported capabilities."""
        return {
            STTCapability.BATCH,
            STTCapability.WORD_TIMESTAMPS,
        }

    def is_available(self) -> bool:
        """Check if ElevenLabs is available.

        Returns:
            True if API key is set and SDK is installed
        """
        if not self.config.api_key:
            return False
        try:
            from elevenlabs.client import ElevenLabs  # noqa: F401

            return True
        except ImportError:
            return False

    def _get_client(self):
        """Lazy client initialization.

        Returns:
            ElevenLabs client instance
        """
        if self._client is None:
            from elevenlabs.client import ElevenLabs

            self._client = ElevenLabs(
                api_key=self.config.api_key,
                timeout=self.config.timeout,
            )
        return self._client

    def transcribe(self, audio_data: bytes, audio_format: str = "wav") -> TranscriptionResult | None:
        """Transcribe audio using ElevenLabs STT API.

        Args:
            audio_data: Raw audio bytes (WAV format expected)
            audio_format: Audio format (currently only "wav" fully supported)

        Returns:
            TranscriptionResult with text and metadata, or None on failure
        """
        if not self.is_available():
            return None

        try:
            client = self._get_client()

            # Wrap audio bytes in BytesIO for API
            audio_buffer = io.BytesIO(audio_data)

            # Determine model to use
            model_id = self.config.model or "scribe_v1"

            # Call ElevenLabs STT
            transcription = client.speech_to_text.convert(
                file=audio_buffer,
                model_id=model_id,
            )

            # Extract text from response
            text = transcription.text if hasattr(transcription, "text") else str(transcription)

            if not text:
                return None

            return TranscriptionResult(
                text=text,
                language=getattr(transcription, "language_code", None),
                is_final=True,
                raw_response={"provider": "elevenlabs", "model": model_id},
            )

        except Exception as e:
            # Import config for debug flag
            from .config import config

            if config.DEBUG:
                print(f"ElevenLabs STT error: {e}")
            # Re-raise to allow fallback handling
            raise
