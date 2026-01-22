"""Tests for ElevenLabs STT Provider.

Tests the ElevenLabsSTTProvider class functionality including:
- Provider initialization and configuration
- Availability checking
- Transcription functionality
- Audio format handling
- Error handling
"""

import io
import wave
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from dicton.stt_provider import STTCapability, STTProviderConfig

# =============================================================================
# Provider Initialization Tests
# =============================================================================


class TestElevenLabsProviderInit:
    """Test ElevenLabs provider initialization."""

    def test_init_without_config(self):
        """Test initialization without explicit config uses environment."""
        with patch.dict("os.environ", {"ELEVENLABS_API_KEY": "test_key"}, clear=False):
            from dicton.stt_elevenlabs import ElevenLabsSTTProvider

            provider = ElevenLabsSTTProvider()
            assert provider._config.api_key == "test_key"

    def test_init_with_config(self):
        """Test initialization with explicit config."""
        from dicton.stt_elevenlabs import ElevenLabsSTTProvider

        config = STTProviderConfig(api_key="explicit_key", model="scribe_v2")
        provider = ElevenLabsSTTProvider(config)
        assert provider._config.api_key == "explicit_key"
        assert provider._config.model == "scribe_v2"

    def test_name_property(self):
        """Test provider name."""
        from dicton.stt_elevenlabs import ElevenLabsSTTProvider

        provider = ElevenLabsSTTProvider()
        assert provider.name == "ElevenLabs Scribe"

    def test_capabilities(self):
        """Test provider capabilities."""
        from dicton.stt_elevenlabs import ElevenLabsSTTProvider

        provider = ElevenLabsSTTProvider()
        caps = provider.capabilities
        assert STTCapability.BATCH in caps
        assert STTCapability.WORD_TIMESTAMPS in caps
        assert STTCapability.STREAMING not in caps
        assert STTCapability.TRANSLATION not in caps


# =============================================================================
# Availability Tests
# =============================================================================


class TestElevenLabsAvailability:
    """Test ElevenLabs provider availability checking."""

    def test_unavailable_without_api_key(self):
        """Test provider is unavailable without API key."""
        with patch.dict("os.environ", {"ELEVENLABS_API_KEY": ""}, clear=False):
            from dicton.stt_elevenlabs import ElevenLabsSTTProvider

            provider = ElevenLabsSTTProvider(STTProviderConfig(api_key=""))
            assert provider.is_available() is False

    def test_available_with_api_key(self):
        """Test provider is available with API key."""
        from dicton.stt_elevenlabs import ElevenLabsSTTProvider

        with patch("elevenlabs.client.ElevenLabs") as mock_elevenlabs:
            mock_client = MagicMock()
            mock_elevenlabs.return_value = mock_client

            provider = ElevenLabsSTTProvider(STTProviderConfig(api_key="test_key"))
            assert provider.is_available() is True
            mock_elevenlabs.assert_called_once()

    def test_unavailable_when_sdk_missing(self):
        """Test provider is unavailable when SDK import fails."""
        from dicton.stt_elevenlabs import ElevenLabsSTTProvider

        # Simulate import error by patching the import inside is_available
        with patch.dict("sys.modules", {"elevenlabs": None, "elevenlabs.client": None}):
            provider = ElevenLabsSTTProvider(STTProviderConfig(api_key="test_key"))
            # Force re-check by clearing state
            provider._api_key_hash = None
            provider._client = None
            assert provider.is_available() is False


# =============================================================================
# Transcription Tests
# =============================================================================


class TestElevenLabsTranscription:
    """Test ElevenLabs transcription functionality."""

    @pytest.fixture
    def mock_provider(self):
        """Create provider with mocked client."""
        from dicton.stt_elevenlabs import ElevenLabsSTTProvider

        mock_client = MagicMock()
        provider = ElevenLabsSTTProvider(STTProviderConfig(api_key="test_key"))
        provider._client = mock_client
        provider._api_key_hash = provider._compute_api_key_hash()
        provider._is_available = True
        yield provider, mock_client

    def test_transcribe_empty_audio_returns_none(self, mock_provider):
        """Test transcribe returns None for empty audio."""
        provider, _ = mock_provider
        assert provider.transcribe(b"") is None
        assert provider.transcribe(None) is None

    def test_transcribe_returns_result(self, mock_provider):
        """Test successful transcription returns result."""
        provider, mock_client = mock_provider

        # Create mock response
        mock_response = MagicMock()
        mock_response.text = "Hello world"
        mock_response.language_code = "en"
        mock_client.speech_to_text.convert.return_value = mock_response

        # Create test WAV audio
        audio = create_test_wav()

        result = provider.transcribe(audio)

        assert result is not None
        assert result.text == "Hello world"
        assert result.language == "en"
        assert result.is_final is True
        mock_client.speech_to_text.convert.assert_called_once()

    def test_transcribe_handles_api_error(self, mock_provider):
        """Test transcribe handles API errors gracefully."""
        provider, mock_client = mock_provider
        mock_client.speech_to_text.convert.side_effect = Exception("API Error")

        audio = create_test_wav()
        result = provider.transcribe(audio)

        assert result is None

    def test_transcribe_raw_pcm_conversion(self, mock_provider):
        """Test transcribe converts raw PCM to WAV."""
        provider, mock_client = mock_provider

        mock_response = MagicMock()
        mock_response.text = "Test"
        mock_response.language_code = "en"
        mock_client.speech_to_text.convert.return_value = mock_response

        # Create raw PCM data (not WAV)
        raw_pcm = np.zeros(16000, dtype=np.int16).tobytes()

        result = provider.transcribe(raw_pcm)

        assert result is not None
        assert result.text == "Test"

        # Verify API was called
        mock_client.speech_to_text.convert.assert_called_once()

    def test_transcribe_with_word_timestamps(self, mock_provider):
        """Test transcription extracts word timestamps."""
        provider, mock_client = mock_provider

        # Create mock response with words
        mock_word1 = MagicMock()
        mock_word1.text = "Hello"
        mock_word1.start = 0.0
        mock_word1.end = 0.5
        mock_word2 = MagicMock()
        mock_word2.text = "world"
        mock_word2.start = 0.5
        mock_word2.end = 1.0

        mock_response = MagicMock()
        mock_response.text = "Hello world"
        mock_response.language_code = "en"
        mock_response.words = [mock_word1, mock_word2]
        mock_client.speech_to_text.convert.return_value = mock_response

        audio = create_test_wav()
        result = provider.transcribe(audio)

        assert result is not None
        assert len(result.words) == 2
        assert result.words[0].word == "Hello"
        assert result.words[0].start == 0.0
        assert result.words[1].word == "world"
        assert result.words[1].end == 1.0


# =============================================================================
# Streaming Tests
# =============================================================================


class TestElevenLabsStreaming:
    """Test ElevenLabs streaming behavior (falls back to batch)."""

    def test_stream_transcribe_uses_batch(self):
        """Test stream_transcribe falls back to batch mode."""
        from dicton.stt_elevenlabs import ElevenLabsSTTProvider

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "Streamed"
        mock_response.language_code = "en"
        mock_client.speech_to_text.convert.return_value = mock_response

        provider = ElevenLabsSTTProvider(STTProviderConfig(api_key="test_key"))
        provider._client = mock_client
        provider._api_key_hash = provider._compute_api_key_hash()
        provider._is_available = True

        # Create audio chunks generator
        audio = create_test_wav()
        chunks = [audio[i : i + 1024] for i in range(0, len(audio), 1024)]

        result = provider.stream_transcribe(iter(chunks))

        assert result is not None
        assert result.text == "Streamed"
        mock_client.speech_to_text.convert.assert_called_once()


# =============================================================================
# Translation Tests
# =============================================================================


class TestElevenLabsTranslation:
    """Test ElevenLabs translation (unsupported)."""

    def test_translate_returns_none(self):
        """Test translate returns None (not supported)."""
        from dicton.stt_elevenlabs import ElevenLabsSTTProvider

        provider = ElevenLabsSTTProvider()
        assert provider.translate(b"audio", "en") is None


# =============================================================================
# Helper Functions
# =============================================================================


def create_test_wav(duration: float = 1.0, sample_rate: int = 16000) -> bytes:
    """Create test WAV audio data.

    Args:
        duration: Audio duration in seconds.
        sample_rate: Sample rate in Hz.

    Returns:
        WAV file bytes.
    """
    samples = int(duration * sample_rate)
    audio = np.zeros(samples, dtype=np.int16)

    wav_buffer = io.BytesIO()
    with wave.open(wav_buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(audio.tobytes())

    wav_buffer.seek(0)
    return wav_buffer.read()
