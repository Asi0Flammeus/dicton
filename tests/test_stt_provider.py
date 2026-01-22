"""Tests for Dicton STT provider (speech recognition engine) module.

Tests the SpeechRecognizer class functionality including:
- Device detection and selection
- Audio recording lifecycle
- Transcription via STT provider abstraction
- Text filtering and noise removal
"""

import wave
from io import BytesIO
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from dicton.stt_provider import NullSTTProvider, TranscriptionResult

# =============================================================================
# Device Selection Tests
# =============================================================================


class TestDeviceSelection:
    """Test audio input device detection and selection."""

    @pytest.fixture
    def mock_pyaudio(self):
        """Create mock PyAudio instance."""
        mock = MagicMock()
        mock.get_device_count.return_value = 3

        # Define device info for mock devices
        devices = [
            {
                "index": 0,
                "name": "HDA Intel PCH",
                "maxInputChannels": 2,
                "defaultSampleRate": 44100,
            },
            {
                "index": 1,
                "name": "pulse",
                "maxInputChannels": 2,
                "defaultSampleRate": 48000,
            },
            {
                "index": 2,
                "name": "USB Microphone",
                "maxInputChannels": 1,
                "defaultSampleRate": 16000,
            },
        ]

        def get_device_info(index):
            return devices[index]

        mock.get_device_info_by_index.side_effect = get_device_info
        mock.get_default_input_device_info.return_value = devices[0]

        return mock

    def test_select_best_device_linux_prefers_pulse(self, mock_pyaudio):
        """Test Linux prefers PulseAudio device."""
        devices = [
            {"index": 0, "name": "HDA Intel", "rate": 44100, "is_default": True},
            {"index": 1, "name": "pulse", "rate": 48000, "is_default": False},
        ]

        with patch("dicton.speech_recognition_engine.IS_LINUX", True), \
             patch("dicton.speech_recognition_engine.IS_WINDOWS", False):
            from dicton.speech_recognition_engine import SpeechRecognizer

            # Create instance without __init__ to test just the method
            recognizer = object.__new__(SpeechRecognizer)
            result = recognizer._select_best_device(devices)

            assert result["name"] == "pulse"
            assert result["index"] == 1

    def test_select_best_device_windows_prefers_default(self, mock_pyaudio):
        """Test Windows prefers default device."""
        devices = [
            {"index": 0, "name": "Realtek Audio", "rate": 44100, "is_default": True},
            {"index": 1, "name": "USB Microphone", "rate": 16000, "is_default": False},
        ]

        with patch("dicton.speech_recognition_engine.IS_LINUX", False), \
             patch("dicton.speech_recognition_engine.IS_WINDOWS", True):
            from dicton.speech_recognition_engine import SpeechRecognizer

            recognizer = object.__new__(SpeechRecognizer)
            result = recognizer._select_best_device(devices)

            assert result["is_default"] is True
            assert result["index"] == 0

    def test_select_best_device_windows_fallback_microphone(self, mock_pyaudio):
        """Test Windows falls back to device with 'microphone' in name."""
        devices = [
            {"index": 0, "name": "Speakers", "rate": 44100, "is_default": False},
            {"index": 1, "name": "USB Microphone", "rate": 16000, "is_default": False},
        ]

        with patch("dicton.speech_recognition_engine.IS_LINUX", False), \
             patch("dicton.speech_recognition_engine.IS_WINDOWS", True):
            from dicton.speech_recognition_engine import SpeechRecognizer

            recognizer = object.__new__(SpeechRecognizer)
            result = recognizer._select_best_device(devices)

            assert result["name"] == "USB Microphone"

    def test_select_best_device_fallback_first(self, mock_pyaudio):
        """Test fallback to first device when no other criteria match."""
        devices = [
            {"index": 0, "name": "Device A", "rate": 44100, "is_default": False},
            {"index": 1, "name": "Device B", "rate": 16000, "is_default": False},
        ]

        with patch("dicton.speech_recognition_engine.IS_LINUX", False), \
             patch("dicton.speech_recognition_engine.IS_WINDOWS", False):
            from dicton.speech_recognition_engine import SpeechRecognizer

            recognizer = object.__new__(SpeechRecognizer)
            result = recognizer._select_best_device(devices)

            assert result["index"] == 0


# =============================================================================
# Text Filter Tests
# =============================================================================


class TestTextFilter:
    """Test text filtering and noise removal."""

    @pytest.fixture
    def recognizer(self):
        """Create SpeechRecognizer with mocked audio subsystem."""
        with patch("dicton.speech_recognition_engine.pyaudio"), \
             patch("dicton.speech_recognition_engine.config") as mock_config, \
             patch("dicton.speech_recognition_engine.get_text_processor") as mock_processor, \
             patch("dicton.speech_recognition_engine.get_stt_provider_with_fallback") as mock_factory:

            mock_config.MIC_DEVICE = "auto"
            mock_config.SAMPLE_RATE = 16000

            # Mock factory to return NullSTTProvider
            mock_factory.return_value = NullSTTProvider()

            # Mock text processor to return input unchanged
            processor_instance = MagicMock()
            processor_instance.process.side_effect = lambda x: x
            mock_processor.return_value = processor_instance

            from dicton.speech_recognition_engine import SpeechRecognizer

            recognizer = object.__new__(SpeechRecognizer)
            recognizer._stt_provider = NullSTTProvider()
            recognizer._provider_available = False
            recognizer.recording = False
            recognizer._cancelled = False
            recognizer.input_device = None

            # Set up text processor mock
            recognizer._processor = processor_instance

            return recognizer

    def test_filter_returns_none_for_empty(self, recognizer):
        """Test filter returns None for empty text."""
        assert recognizer._filter("") is None
        assert recognizer._filter(None) is None
        assert recognizer._filter("ab") is None  # Less than 3 chars

    def test_filter_removes_noise_phrases(self, recognizer):
        """Test filter removes common noise phrases."""
        noise_phrases = [
            "thanks for watching",
            "Thank you for watching",
            "subscribe",
            "you",
            "thank you",
            "merci",
            "bye",
            "ok",
            "okay",
            "um",
            "uh",
            "hmm",
            "huh",
            "ah",
            "oh",
            "eh",
        ]

        for phrase in noise_phrases:
            assert recognizer._filter(phrase) is None, f"'{phrase}' should be filtered"

    def test_filter_removes_single_short_words(self, recognizer):
        """Test filter removes single short words."""
        short_words = ["yes", "no", "word", "test123"]

        for word in short_words:
            assert recognizer._filter(word) is None, f"'{word}' should be filtered"

    def test_filter_keeps_valid_text(self, recognizer):
        """Test filter keeps valid sentences."""
        with patch("dicton.speech_recognition_engine.get_text_processor") as mock_proc:
            processor = MagicMock()
            processor.process.side_effect = lambda x: x
            mock_proc.return_value = processor

            valid_texts = [
                "Hello world",
                "This is a test sentence",
                "The quick brown fox",
            ]

            for text in valid_texts:
                result = recognizer._filter(text)
                assert result == text, f"'{text}' should be kept"

    def test_filter_applies_text_processor(self, recognizer):
        """Test filter applies text processor."""
        with patch("dicton.speech_recognition_engine.get_text_processor") as mock_proc:
            processor = MagicMock()
            processor.process.return_value = "processed text here"
            mock_proc.return_value = processor

            result = recognizer._filter("original text here")

            processor.process.assert_called_once()
            assert result == "processed text here"


# =============================================================================
# Recording Lifecycle Tests
# =============================================================================


class TestRecordingLifecycle:
    """Test recording start/stop/cancel lifecycle."""

    def test_stop_sets_recording_flag(self):
        """Test stop() sets recording flag to False."""
        with patch("dicton.speech_recognition_engine.pyaudio"), \
             patch("dicton.speech_recognition_engine.config"), \
             patch("dicton.speech_recognition_engine.get_stt_provider_with_fallback") as mock_factory:

            mock_factory.return_value = NullSTTProvider()

            from dicton.speech_recognition_engine import SpeechRecognizer

            recognizer = object.__new__(SpeechRecognizer)
            recognizer.recording = True

            recognizer.stop()

            assert recognizer.recording is False

    def test_cancel_sets_cancelled_flag(self):
        """Test cancel() sets both cancelled and recording flags."""
        with patch("dicton.speech_recognition_engine.pyaudio"), \
             patch("dicton.speech_recognition_engine.config"), \
             patch("dicton.speech_recognition_engine.get_stt_provider_with_fallback") as mock_factory:

            mock_factory.return_value = NullSTTProvider()

            from dicton.speech_recognition_engine import SpeechRecognizer

            recognizer = object.__new__(SpeechRecognizer)
            recognizer.recording = True
            recognizer._cancelled = False

            recognizer.cancel()

            assert recognizer.recording is False
            assert recognizer._cancelled is True

    def test_record_returns_none_without_provider(self):
        """Test record() returns None when no STT provider available."""
        with patch("dicton.speech_recognition_engine.pyaudio"), \
             patch("dicton.speech_recognition_engine.config"), \
             patch("dicton.speech_recognition_engine.get_stt_provider_with_fallback") as mock_factory:

            mock_factory.return_value = NullSTTProvider()

            from dicton.speech_recognition_engine import SpeechRecognizer

            recognizer = object.__new__(SpeechRecognizer)
            recognizer._stt_provider = NullSTTProvider()
            recognizer._provider_available = False

            result = recognizer.record()

            assert result is None


# =============================================================================
# Transcription Tests
# =============================================================================


class TestTranscription:
    """Test audio transcription functionality."""

    def test_transcribe_returns_none_for_empty_audio(self):
        """Test transcribe() returns None for empty audio."""
        with patch("dicton.speech_recognition_engine.pyaudio"), \
             patch("dicton.speech_recognition_engine.config"), \
             patch("dicton.speech_recognition_engine.get_stt_provider_with_fallback") as mock_factory:

            mock_provider = MagicMock()
            mock_provider.is_available.return_value = True
            mock_factory.return_value = mock_provider

            from dicton.speech_recognition_engine import SpeechRecognizer

            recognizer = object.__new__(SpeechRecognizer)
            recognizer._stt_provider = mock_provider
            recognizer._provider_available = True

            assert recognizer.transcribe(None) is None
            assert recognizer.transcribe(np.array([])) is None

    def test_transcribe_returns_none_without_provider(self):
        """Test transcribe() returns None when no STT provider available."""
        with patch("dicton.speech_recognition_engine.pyaudio"), \
             patch("dicton.speech_recognition_engine.config"), \
             patch("dicton.speech_recognition_engine.get_stt_provider_with_fallback") as mock_factory:

            mock_factory.return_value = NullSTTProvider()

            from dicton.speech_recognition_engine import SpeechRecognizer

            recognizer = object.__new__(SpeechRecognizer)
            recognizer._stt_provider = NullSTTProvider()
            recognizer._provider_available = False

            audio = np.random.randn(16000).astype(np.float32)
            result = recognizer.transcribe(audio)

            assert result is None

    def test_transcribe_calls_provider_api(self):
        """Test transcribe() calls STT provider with correct format."""
        with patch("dicton.speech_recognition_engine.pyaudio"), \
             patch("dicton.speech_recognition_engine.config") as mock_config, \
             patch("dicton.speech_recognition_engine.get_stt_provider_with_fallback") as mock_factory, \
             patch("dicton.speech_recognition_engine.get_text_processor") as mock_proc:

            mock_config.SAMPLE_RATE = 16000
            mock_config.DEBUG = False

            processor = MagicMock()
            processor.process.side_effect = lambda x: x
            mock_proc.return_value = processor

            # Create mock provider that returns transcription result
            mock_provider = MagicMock()
            mock_provider.transcribe.return_value = TranscriptionResult(
                text="Hello world transcription"
            )
            mock_factory.return_value = mock_provider

            from dicton.speech_recognition_engine import SpeechRecognizer

            recognizer = object.__new__(SpeechRecognizer)
            recognizer._stt_provider = mock_provider
            recognizer._provider_available = True

            # Create test audio (1 second of silence)
            audio = np.zeros(16000, dtype=np.float32)
            result = recognizer.transcribe(audio)

            # Verify provider was called
            mock_provider.transcribe.assert_called_once()

            # Result should be the transcription text
            assert result == "Hello world transcription"

    def test_transcribe_handles_api_error(self):
        """Test transcribe() handles API errors gracefully."""
        with patch("dicton.speech_recognition_engine.pyaudio"), \
             patch("dicton.speech_recognition_engine.config") as mock_config, \
             patch("dicton.speech_recognition_engine.get_stt_provider_with_fallback") as mock_factory:

            mock_config.SAMPLE_RATE = 16000
            mock_config.DEBUG = False

            # Create mock provider that raises exception
            mock_provider = MagicMock()
            mock_provider.transcribe.side_effect = Exception("API Error")
            mock_factory.return_value = mock_provider

            from dicton.speech_recognition_engine import SpeechRecognizer

            recognizer = object.__new__(SpeechRecognizer)
            recognizer._stt_provider = mock_provider
            recognizer._provider_available = True

            audio = np.zeros(16000, dtype=np.float32)
            result = recognizer.transcribe(audio)

            assert result is None


# =============================================================================
# Audio Conversion Tests
# =============================================================================


class TestAudioConversion:
    """Test audio format conversion for transcription."""

    def test_wav_format_correct(self):
        """Test WAV file is created with correct format."""
        with patch("dicton.speech_recognition_engine.pyaudio"), \
             patch("dicton.speech_recognition_engine.config") as mock_config, \
             patch("dicton.speech_recognition_engine.get_stt_provider_with_fallback") as mock_factory, \
             patch("dicton.speech_recognition_engine.get_text_processor") as mock_proc:

            mock_config.SAMPLE_RATE = 16000
            mock_config.DEBUG = False

            processor = MagicMock()
            processor.process.side_effect = lambda x: x
            mock_proc.return_value = processor

            from dicton.speech_recognition_engine import SpeechRecognizer

            recognizer = object.__new__(SpeechRecognizer)

            # Capture the WAV bytes sent to provider
            captured_wav = None

            def capture_transcribe(audio_bytes):
                nonlocal captured_wav
                captured_wav = audio_bytes
                return TranscriptionResult(text="test transcription")

            mock_provider = MagicMock()
            mock_provider.transcribe.side_effect = capture_transcribe
            mock_factory.return_value = mock_provider

            recognizer._stt_provider = mock_provider
            recognizer._provider_available = True

            # Create test audio
            audio = np.random.randn(16000).astype(np.float32) * 0.5
            recognizer.transcribe(audio)

            # Verify WAV format
            assert captured_wav is not None
            wav_buffer = BytesIO(captured_wav)

            with wave.open(wav_buffer, "rb") as wav:
                assert wav.getnchannels() == 1
                assert wav.getsampwidth() == 2  # 16-bit
                assert wav.getframerate() == 16000


# =============================================================================
# Integration Tests (require API key)
# =============================================================================


@pytest.mark.integration
class TestSTTIntegration:
    """Integration tests requiring actual ElevenLabs API key.

    Run with: pytest --run-integration
    """

    def test_elevenlabs_connection(self):
        """Test ElevenLabs client can be initialized."""
        import os

        api_key = os.getenv("ELEVENLABS_API_KEY")
        if not api_key:
            pytest.skip("ELEVENLABS_API_KEY not set")

        try:
            from elevenlabs.client import ElevenLabs
            client = ElevenLabs(api_key=api_key)
            assert client is not None
        except ImportError:
            pytest.skip("elevenlabs package not installed")

    def test_transcribe_real_audio(self):
        """Test transcription with real (generated) audio."""
        import os

        api_key = os.getenv("ELEVENLABS_API_KEY")
        if not api_key:
            pytest.skip("ELEVENLABS_API_KEY not set")

        # This test would need actual audio data
        # For now, skip with a note
        pytest.skip("Real audio transcription test requires audio samples")
