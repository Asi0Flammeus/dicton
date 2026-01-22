"""Tests for Mistral STT Provider.

Tests the MistralSTTProvider class functionality including:
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


class TestMistralProviderInit:
    """Test Mistral provider initialization."""

    def test_init_without_config(self):
        """Test initialization without explicit config uses environment."""
        with patch.dict("os.environ", {"MISTRAL_API_KEY": "test_key"}, clear=False):
            from dicton.stt_mistral import MistralSTTProvider

            provider = MistralSTTProvider()
            assert provider._config.api_key == "test_key"

    def test_init_with_config(self):
        """Test initialization with explicit config."""
        from dicton.stt_mistral import MistralSTTProvider

        config = STTProviderConfig(api_key="explicit_key", model="voxtral-custom")
        provider = MistralSTTProvider(config)
        assert provider._config.api_key == "explicit_key"
        assert provider._config.model == "voxtral-custom"

    def test_name_property(self):
        """Test provider name."""
        from dicton.stt_mistral import MistralSTTProvider

        provider = MistralSTTProvider()
        assert provider.name == "Mistral Voxtral"

    def test_capabilities(self):
        """Test provider capabilities."""
        from dicton.stt_mistral import MistralSTTProvider

        provider = MistralSTTProvider()
        caps = provider.capabilities
        assert STTCapability.BATCH in caps
        assert STTCapability.WORD_TIMESTAMPS in caps
        assert STTCapability.STREAMING not in caps
        assert STTCapability.TRANSLATION not in caps


# =============================================================================
# Availability Tests
# =============================================================================


class TestMistralAvailability:
    """Test Mistral provider availability checking."""

    def test_unavailable_without_api_key(self):
        """Test provider is unavailable without API key."""
        with patch.dict("os.environ", {"MISTRAL_API_KEY": ""}, clear=False):
            from dicton.stt_mistral import MistralSTTProvider

            provider = MistralSTTProvider(STTProviderConfig(api_key=""))
            assert provider.is_available() is False

    def test_available_with_api_key(self):
        """Test provider is available with API key."""
        from dicton.stt_mistral import MistralSTTProvider

        with patch("mistralai.Mistral") as mock_mistral:
            mock_client = MagicMock()
            mock_mistral.return_value = mock_client

            provider = MistralSTTProvider(STTProviderConfig(api_key="test_key"))
            assert provider.is_available() is True
            mock_mistral.assert_called_once_with(api_key="test_key")

    def test_unavailable_when_sdk_missing(self):
        """Test provider is unavailable when SDK import fails."""
        from dicton.stt_mistral import MistralSTTProvider

        # Simulate import error by patching the import inside is_available
        with patch.dict("sys.modules", {"mistralai": None}):
            provider = MistralSTTProvider(STTProviderConfig(api_key="test_key"))
            # Force re-check by clearing state
            provider._api_key_hash = None
            provider._client = None
            assert provider.is_available() is False


# =============================================================================
# Transcription Tests
# =============================================================================


class TestMistralTranscription:
    """Test Mistral transcription functionality."""

    @pytest.fixture
    def mock_provider(self):
        """Create provider with mocked client."""
        from dicton.stt_mistral import MistralSTTProvider

        mock_client = MagicMock()
        provider = MistralSTTProvider(STTProviderConfig(api_key="test_key"))
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
        mock_response.language = "en"
        mock_client.audio.transcriptions.complete.return_value = mock_response

        # Create test WAV audio
        audio = create_test_wav()

        result = provider.transcribe(audio)

        assert result is not None
        assert result.text == "Hello world"
        assert result.language == "en"
        assert result.is_final is True
        mock_client.audio.transcriptions.complete.assert_called_once()

    def test_transcribe_handles_api_error(self, mock_provider):
        """Test transcribe handles API errors gracefully."""
        provider, mock_client = mock_provider
        mock_client.audio.transcriptions.complete.side_effect = Exception("API Error")

        audio = create_test_wav()
        result = provider.transcribe(audio)

        assert result is None

    def test_transcribe_raw_pcm_conversion(self, mock_provider):
        """Test transcribe converts raw PCM to WAV."""
        provider, mock_client = mock_provider

        mock_response = MagicMock()
        mock_response.text = "Test"
        mock_response.language = "en"
        mock_client.audio.transcriptions.complete.return_value = mock_response

        # Create raw PCM data (not WAV)
        raw_pcm = np.zeros(16000, dtype=np.int16).tobytes()

        result = provider.transcribe(raw_pcm)

        assert result is not None
        assert result.text == "Test"

        # Verify WAV was sent to API
        call_args = mock_client.audio.transcriptions.complete.call_args
        file_arg = call_args.kwargs.get("file", call_args.args[0] if call_args.args else None)
        assert file_arg is not None

    def test_transcribe_with_word_timestamps(self, mock_provider):
        """Test transcription extracts word timestamps."""
        provider, mock_client = mock_provider

        # Create mock response with words
        mock_word1 = MagicMock()
        mock_word1.word = "Hello"
        mock_word1.start = 0.0
        mock_word1.end = 0.5
        mock_word2 = MagicMock()
        mock_word2.word = "world"
        mock_word2.start = 0.5
        mock_word2.end = 1.0

        mock_response = MagicMock()
        mock_response.text = "Hello world"
        mock_response.language = "en"
        mock_response.words = [mock_word1, mock_word2]
        mock_client.audio.transcriptions.complete.return_value = mock_response

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


class TestMistralStreaming:
    """Test Mistral streaming behavior (falls back to batch)."""

    def test_stream_transcribe_uses_batch(self):
        """Test stream_transcribe falls back to batch mode."""
        from dicton.stt_mistral import MistralSTTProvider

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "Streamed"
        mock_response.language = "en"
        mock_client.audio.transcriptions.complete.return_value = mock_response

        provider = MistralSTTProvider(STTProviderConfig(api_key="test_key"))
        provider._client = mock_client
        provider._api_key_hash = provider._compute_api_key_hash()
        provider._is_available = True

        # Create audio chunks generator
        audio = create_test_wav()
        chunks = [audio[i:i+1024] for i in range(0, len(audio), 1024)]

        result = provider.stream_transcribe(iter(chunks))

        assert result is not None
        assert result.text == "Streamed"
        mock_client.audio.transcriptions.complete.assert_called_once()


# =============================================================================
# Translation Tests
# =============================================================================


class TestMistralTranslation:
    """Test Mistral translation (unsupported)."""

    def test_translate_returns_none(self):
        """Test translate returns None (not supported)."""
        from dicton.stt_mistral import MistralSTTProvider

        provider = MistralSTTProvider()
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
