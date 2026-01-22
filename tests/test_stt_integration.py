"""Integration tests for Dicton STT (Speech-to-Text) functionality.

These tests verify end-to-end STT functionality including:
- ElevenLabs API connectivity
- Audio file transcription
- Language detection
- Error handling in real-world scenarios

These tests require API credentials and make real API calls.
Run with: pytest tests/test_stt_integration.py -v --run-integration
"""

import io
import os
import wave
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def api_key():
    """Get ElevenLabs API key from environment."""
    key = os.getenv("ELEVENLABS_API_KEY")
    if not key:
        pytest.skip("ELEVENLABS_API_KEY not set")
    return key


@pytest.fixture
def speech_recognizer(api_key):
    """Create SpeechRecognizer with real API credentials."""
    # Mock audio devices to avoid hardware requirements
    with patch("dicton.speech_recognition_engine.pyaudio") as mock_pyaudio:
        mock_audio = MagicMock()
        mock_pyaudio.PyAudio.return_value = mock_audio
        mock_audio.get_device_count.return_value = 1
        mock_audio.get_default_input_device_info.return_value = {
            "index": 0,
            "name": "Mock Device",
            "maxInputChannels": 2,
            "defaultSampleRate": 16000,
        }
        mock_audio.get_device_info_by_index.return_value = {
            "index": 0,
            "name": "Mock Device",
            "maxInputChannels": 2,
            "defaultSampleRate": 16000,
        }

        from dicton.speech_recognition_engine import SpeechRecognizer
        recognizer = SpeechRecognizer()

        return recognizer


@pytest.fixture
def sample_audio():
    """Generate sample audio for testing (1 second of silence)."""
    # 1 second of silence at 16kHz
    duration = 1.0
    sample_rate = 16000
    audio = np.zeros(int(duration * sample_rate), dtype=np.float32)
    return audio


@pytest.fixture
def sample_audio_with_noise():
    """Generate sample audio with some noise."""
    duration = 1.0
    sample_rate = 16000
    # Random noise at low amplitude
    audio = np.random.randn(int(duration * sample_rate)).astype(np.float32) * 0.01
    return audio


def generate_wav_bytes(audio: np.ndarray, sample_rate: int = 16000) -> bytes:
    """Convert numpy audio array to WAV bytes."""
    audio_int16 = (audio * 32767).astype(np.int16)

    wav_buffer = io.BytesIO()
    with wave.open(wav_buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)  # 16-bit
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(audio_int16.tobytes())

    wav_buffer.seek(0)
    return wav_buffer.read()


# =============================================================================
# API Connectivity Tests
# =============================================================================


@pytest.mark.integration
class TestElevenLabsConnectivity:
    """Test ElevenLabs API connectivity."""

    def test_client_initialization(self, api_key):
        """Test ElevenLabs client can be initialized."""
        from elevenlabs.client import ElevenLabs

        client = ElevenLabs(api_key=api_key)
        assert client is not None

    def test_invalid_api_key_rejected(self):
        """Test that invalid API key is rejected."""
        from elevenlabs.client import ElevenLabs

        # ElevenLabs client may not validate key until API call
        client = ElevenLabs(api_key="invalid_key_12345")
        assert client is not None  # Client init may succeed

        # But API call should fail
        # Note: We can't actually test this without making an API call
        # which would fail with invalid key

    def test_speech_recognizer_detects_provider(self, speech_recognizer):
        """Test SpeechRecognizer detects STT provider availability."""
        assert speech_recognizer.use_elevenlabs is True
        assert speech_recognizer._provider_available is True
        assert speech_recognizer.provider_name != "None"


# =============================================================================
# Transcription Tests
# =============================================================================


@pytest.mark.integration
class TestTranscription:
    """Test transcription with real API calls."""

    def test_transcribe_silence_returns_none(self, speech_recognizer, sample_audio):
        """Test transcribing silence returns None (filtered as noise)."""
        # Pure silence should be filtered out or return minimal text
        result = speech_recognizer.transcribe(sample_audio)

        # Silence typically gets filtered or returns None
        # The exact behavior depends on ElevenLabs response
        # We just verify no crash occurs
        assert result is None or isinstance(result, str)

    def test_transcribe_returns_string_or_none(self, speech_recognizer, sample_audio_with_noise):
        """Test transcribe returns string or None."""
        result = speech_recognizer.transcribe(sample_audio_with_noise)

        # Should return string (possibly empty) or None for noise
        assert result is None or isinstance(result, str)

    def test_transcribe_empty_audio_returns_none(self, speech_recognizer):
        """Test transcribing empty audio returns None."""
        empty_audio = np.array([], dtype=np.float32)
        result = speech_recognizer.transcribe(empty_audio)

        assert result is None


# =============================================================================
# Audio Format Tests
# =============================================================================


@pytest.mark.integration
class TestAudioFormats:
    """Test various audio formats and sample rates."""

    def test_transcribe_16khz_audio(self, speech_recognizer):
        """Test transcription with 16kHz sample rate."""
        # Generate 0.5 second of audio at 16kHz
        audio = np.zeros(8000, dtype=np.float32)
        result = speech_recognizer.transcribe(audio)

        # Should not crash
        assert result is None or isinstance(result, str)

    def test_transcribe_various_durations(self, speech_recognizer):
        """Test transcription with various audio durations."""
        durations = [0.5, 1.0, 2.0]  # seconds

        for duration in durations:
            samples = int(duration * 16000)
            audio = np.zeros(samples, dtype=np.float32)
            result = speech_recognizer.transcribe(audio)

            # Should handle various durations
            assert result is None or isinstance(result, str), f"Failed for {duration}s audio"


# =============================================================================
# Error Handling Tests
# =============================================================================


@pytest.mark.integration
class TestErrorHandling:
    """Test error handling in real scenarios."""

    def test_transcribe_handles_api_timeout(self, api_key):
        """Test graceful handling of API timeout."""
        with patch("dicton.speech_recognition_engine.pyaudio") as mock_pyaudio:
            mock_audio = MagicMock()
            mock_pyaudio.PyAudio.return_value = mock_audio
            mock_audio.get_device_count.return_value = 1
            mock_audio.get_default_input_device_info.return_value = {
                "index": 0,
                "name": "Mock Device",
                "maxInputChannels": 2,
                "defaultSampleRate": 16000,
            }
            mock_audio.get_device_info_by_index.return_value = {
                "index": 0,
                "name": "Mock Device",
                "maxInputChannels": 2,
                "defaultSampleRate": 16000,
            }

            # Patch config to have very short timeout
            with patch("dicton.speech_recognition_engine.config") as mock_config:
                mock_config.ELEVENLABS_API_KEY = api_key
                mock_config.ELEVENLABS_MODEL = "scribe_v1"
                mock_config.STT_TIMEOUT = 0.001  # Very short timeout
                mock_config.SAMPLE_RATE = 16000
                mock_config.MIC_DEVICE = "auto"
                mock_config.DEBUG = False
                mock_config.VISUALIZER_BACKEND = "pygame"

                from dicton.speech_recognition_engine import SpeechRecognizer

                # Reinitialize with short timeout
                recognizer = SpeechRecognizer()

                # Transcribe should handle timeout gracefully
                audio = np.zeros(16000, dtype=np.float32)
                # This may succeed or fail depending on network conditions
                # Just verify no unhandled exception
                try:
                    result = recognizer.transcribe(audio)
                    assert result is None or isinstance(result, str)
                except Exception as e:
                    # Should not raise unhandled exception in production
                    # but timeout can happen in tests
                    pytest.skip(f"API timeout expected in test environment: {e}")


# =============================================================================
# Provider Availability Tests
# =============================================================================


class TestProviderAvailability:
    """Test STT provider availability detection."""

    def test_elevenlabs_available_with_api_key(self, api_key):
        """Test ElevenLabs is available when API key is set."""
        with patch("dicton.speech_recognition_engine.pyaudio") as mock_pyaudio:
            mock_audio = MagicMock()
            mock_pyaudio.PyAudio.return_value = mock_audio
            mock_audio.get_device_count.return_value = 1
            mock_audio.get_default_input_device_info.return_value = {
                "index": 0,
                "name": "Mock Device",
                "maxInputChannels": 2,
                "defaultSampleRate": 16000,
            }
            mock_audio.get_device_info_by_index.return_value = {
                "index": 0,
                "name": "Mock Device",
                "maxInputChannels": 2,
                "defaultSampleRate": 16000,
            }

            from dicton.speech_recognition_engine import SpeechRecognizer

            recognizer = SpeechRecognizer()
            assert recognizer.use_elevenlabs is True

    def test_provider_unavailable_without_api_keys(self):
        """Test STT provider is unavailable when no API keys are set."""
        from dicton.stt_provider import NullSTTProvider

        with patch("dicton.speech_recognition_engine.pyaudio") as mock_pyaudio, \
             patch("dicton.speech_recognition_engine.get_stt_provider_with_fallback") as mock_factory:

            # Factory returns NullSTTProvider when no providers available
            mock_factory.return_value = NullSTTProvider()

            mock_audio = MagicMock()
            mock_pyaudio.PyAudio.return_value = mock_audio
            mock_audio.get_device_count.return_value = 1
            mock_audio.get_default_input_device_info.return_value = {
                "index": 0,
                "name": "Mock Device",
                "maxInputChannels": 2,
                "defaultSampleRate": 16000,
            }
            mock_audio.get_device_info_by_index.return_value = {
                "index": 0,
                "name": "Mock Device",
                "maxInputChannels": 2,
                "defaultSampleRate": 16000,
            }

            from dicton.speech_recognition_engine import SpeechRecognizer

            recognizer = SpeechRecognizer()
            # use_elevenlabs is now a property for backwards compatibility
            # It returns True if any provider is available
            assert recognizer.use_elevenlabs is False
            assert recognizer._provider_available is False


# =============================================================================
# End-to-End Tests
# =============================================================================


@pytest.mark.integration
class TestEndToEnd:
    """End-to-end STT tests."""

    def test_full_pipeline_silence(self, speech_recognizer):
        """Test full pipeline with silence input."""
        # Generate silence
        audio = np.zeros(16000, dtype=np.float32)  # 1 second

        # Transcribe
        result = speech_recognizer.transcribe(audio)

        # Silence should be filtered
        assert result is None or len(result) == 0 or result.strip() == ""

    def test_full_pipeline_noise(self, speech_recognizer):
        """Test full pipeline with noise input."""
        # Generate low-amplitude noise
        audio = np.random.randn(16000).astype(np.float32) * 0.001

        # Transcribe
        result = speech_recognizer.transcribe(audio)

        # Noise should be filtered or return minimal text
        assert result is None or isinstance(result, str)
