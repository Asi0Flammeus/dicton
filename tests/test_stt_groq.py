"""Tests for Groq STT Provider."""

from __future__ import annotations

import io
import wave
from unittest.mock import MagicMock

import numpy as np

from dicton.adapters.stt.groq import GroqSTTProvider
from dicton.adapters.stt.provider import STTProviderConfig


def create_test_wav(duration: float = 0.1, sample_rate: int = 16000) -> bytes:
    """Create a small valid WAV file for transcription tests."""
    samples = int(duration * sample_rate)
    audio_data = np.zeros(samples, dtype=np.int16)

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(audio_data.tobytes())
    return buffer.getvalue()


def test_transcribe_sends_french_language_hint():
    provider = GroqSTTProvider(STTProviderConfig(api_key="test_key"))
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = "Bonjour le monde"
    mock_response.language = "fr"
    mock_client.audio.transcriptions.create.return_value = mock_response
    provider._client = mock_client
    provider._is_available = True
    provider._ensure_client = lambda: True  # type: ignore[method-assign]

    result = provider.transcribe(create_test_wav())

    assert result is not None
    assert result.text == "Bonjour le monde"
    mock_client.audio.transcriptions.create.assert_called_once()
    assert mock_client.audio.transcriptions.create.call_args.kwargs["language"] == "fr"
