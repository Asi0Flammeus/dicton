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
        from dicton import stt_factory

        stt_factory._PROVIDER_REGISTRY.clear()
        stt_factory._provider_cache.clear()
        yield
        stt_factory._PROVIDER_REGISTRY.clear()
        stt_factory._provider_cache.clear()

    @pytest.fixture
    def mock_audio_deps(self):
        """Mock audio-related dependencies."""
        with patch.dict("sys.modules", {
            "pyaudio": MagicMock(),
        }):
            yield

    def test_recognizer_uses_factory(self, mock_audio_deps):
        """Test that SpeechRecognizer uses the STT factory."""
        with patch.dict("os.environ", {
            "STT_PROVIDER": "mistral",
            "MISTRAL_API_KEY": "test_key",
        }, clear=False), \
             patch("dicton.stt_mistral._get_mistral_client") as mock_get, \
             patch("dicton.speech_recognition_engine.pyaudio") as mock_pyaudio:

            mock_get.return_value = MagicMock()
            mock_pyaudio.PyAudio.return_value = MagicMock()

            # Clear module cache
            import dicton.stt_mistral as mistral_module
            mistral_module._mistral_client = None

            from dicton.speech_recognition_engine import SpeechRecognizer

            recognizer = SpeechRecognizer()

            # Verify provider was initialized from factory
            assert recognizer._provider_available
            assert recognizer.provider_name == "Mistral Voxtral"

    def test_recognizer_respects_stt_provider_config(self, mock_audio_deps):
        """Test that STT_PROVIDER env var is respected."""
        with patch.dict("os.environ", {
            "STT_PROVIDER": "elevenlabs",
            "ELEVENLABS_API_KEY": "test_key",
        }, clear=False), \
             patch("dicton.stt_elevenlabs._get_elevenlabs_client") as mock_get, \
             patch("dicton.speech_recognition_engine.pyaudio") as mock_pyaudio:

            mock_get.return_value = MagicMock()
            mock_pyaudio.PyAudio.return_value = MagicMock()

            # Clear module cache
            import dicton.stt_elevenlabs as el_module
            el_module._elevenlabs_client = None

            from dicton.speech_recognition_engine import SpeechRecognizer

            recognizer = SpeechRecognizer()

            assert recognizer._provider_available
            assert "ElevenLabs" in recognizer.provider_name

    def test_recognizer_graceful_degradation(self, mock_audio_deps):
        """Test graceful degradation when no provider is available."""
        with patch.dict("os.environ", {
            "STT_PROVIDER": "",
            "MISTRAL_API_KEY": "",
            "ELEVENLABS_API_KEY": "",
        }, clear=False), \
             patch("dicton.speech_recognition_engine.pyaudio") as mock_pyaudio:

            mock_pyaudio.PyAudio.return_value = MagicMock()

            from dicton.speech_recognition_engine import SpeechRecognizer

            recognizer = SpeechRecognizer()

            # Should degrade gracefully to NullSTTProvider
            assert not recognizer._provider_available
            assert recognizer.provider_name == "None"

    def test_use_elevenlabs_backwards_compat(self, mock_audio_deps):
        """Test use_elevenlabs property for backwards compatibility."""
        with patch.dict("os.environ", {
            "STT_PROVIDER": "mistral",
            "MISTRAL_API_KEY": "test_key",
        }, clear=False), \
             patch("dicton.stt_mistral._get_mistral_client") as mock_get, \
             patch("dicton.speech_recognition_engine.pyaudio") as mock_pyaudio:

            mock_get.return_value = MagicMock()
            mock_pyaudio.PyAudio.return_value = MagicMock()

            import dicton.stt_mistral as mistral_module
            mistral_module._mistral_client = None

            from dicton.speech_recognition_engine import SpeechRecognizer

            recognizer = SpeechRecognizer()

            # use_elevenlabs should return True when any provider is available
            assert recognizer.use_elevenlabs is True

    def test_provider_switching_via_config(self, mock_audio_deps):
        """Test that different STT_PROVIDER values result in different providers."""
        test_cases = [
            ("mistral", "MISTRAL_API_KEY", "Mistral Voxtral"),
            ("elevenlabs", "ELEVENLABS_API_KEY", "ElevenLabs Scribe"),
        ]

        for provider_name, api_key_var, expected_name in test_cases:
            # Reset factory state
            from dicton import stt_factory
            stt_factory._PROVIDER_REGISTRY.clear()
            stt_factory._provider_cache.clear()

            with patch.dict("os.environ", {
                "STT_PROVIDER": provider_name,
                api_key_var: "test_key",
            }, clear=False), \
                 patch(f"dicton.stt_{provider_name}._get_{provider_name}_client") as mock_get, \
                 patch("dicton.speech_recognition_engine.pyaudio") as mock_pyaudio:

                mock_get.return_value = MagicMock()
                mock_pyaudio.PyAudio.return_value = MagicMock()

                # Clear module cache
                if provider_name == "mistral":
                    import dicton.stt_mistral as mod
                    mod._mistral_client = None
                elif provider_name == "elevenlabs":
                    import dicton.stt_elevenlabs as mod
                    mod._elevenlabs_client = None

                from dicton.speech_recognition_engine import SpeechRecognizer

                recognizer = SpeechRecognizer()

                assert recognizer.provider_name == expected_name, \
                    f"Expected {expected_name} for {provider_name}, got {recognizer.provider_name}"
