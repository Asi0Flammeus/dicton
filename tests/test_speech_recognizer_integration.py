"""Integration tests for SpeechRecognizer with STT Factory.

Tests verify that SpeechRecognizer properly integrates with the STT
provider factory system, respecting STT_PROVIDER configuration.

Note: These tests mock heavy dependencies (pyaudio, numpy) since we're
testing the integration logic, not the audio capture functionality.
"""

from unittest.mock import MagicMock, patch

import pytest

# Skip these tests by default - they require mocking heavy dependencies
pytestmark = pytest.mark.skip(reason="Integration tests require full environment")


class TestSpeechRecognizerIntegration:
    """Test SpeechRecognizer integration with STT factory."""

    @pytest.fixture(autouse=True)
    def reset_factory(self):
        """Reset factory state before each test."""
        from dicton.adapters.stt import factory as stt_factory

        stt_factory._PROVIDER_REGISTRY.clear()
        stt_factory._provider_cache.clear()
        yield
        stt_factory._PROVIDER_REGISTRY.clear()
        stt_factory._provider_cache.clear()

    @pytest.fixture
    def mock_audio_deps(self):
        """Mock audio-related dependencies."""
        with patch.dict(
            "sys.modules",
            {
                "pyaudio": MagicMock(),
            },
        ):
            yield

    def test_recognizer_uses_factory(self, mock_audio_deps):
        """Test that SpeechRecognizer uses the STT factory."""
        mock_groq_module = MagicMock()
        with (
            patch.dict(
                "os.environ",
                {
                    "STT_PROVIDER": "groq",
                    "GROQ_API_KEY": "test_key",
                },
                clear=False,
            ),
            patch.dict("sys.modules", {"groq": mock_groq_module}),
            patch("dicton.adapters.audio.recognizer.pyaudio") as mock_pyaudio,
        ):
            mock_pyaudio.PyAudio.return_value = MagicMock()

            from dicton.adapters.audio.recognizer import SpeechRecognizer

            recognizer = SpeechRecognizer()

            assert recognizer._provider_available
            assert recognizer.provider_name == "Groq Whisper"

    def test_recognizer_respects_stt_provider_config(self, mock_audio_deps):
        """Test that STT_PROVIDER env var is respected."""
        with (
            patch.dict(
                "os.environ",
                {
                    "STT_PROVIDER": "elevenlabs",
                    "ELEVENLABS_API_KEY": "test_key",
                },
                clear=False,
            ),
            patch("dicton.adapters.audio.recognizer.pyaudio") as mock_pyaudio,
        ):
            mock_pyaudio.PyAudio.return_value = MagicMock()

            from dicton.adapters.audio.recognizer import SpeechRecognizer

            recognizer = SpeechRecognizer()

            assert recognizer._provider_available
            assert "ElevenLabs" in recognizer.provider_name

    def test_recognizer_graceful_degradation(self, mock_audio_deps):
        """Test graceful degradation when no provider is available."""
        with (
            patch.dict(
                "os.environ",
                {
                    "STT_PROVIDER": "",
                    "GROQ_API_KEY": "",
                    "ELEVENLABS_API_KEY": "",
                },
                clear=False,
            ),
            patch("dicton.adapters.audio.recognizer.pyaudio") as mock_pyaudio,
        ):
            mock_pyaudio.PyAudio.return_value = MagicMock()

            from dicton.adapters.audio.recognizer import SpeechRecognizer

            recognizer = SpeechRecognizer()

            assert not recognizer._provider_available
            assert recognizer.provider_name == "None"
