"""STT Provider Abstraction for Dicton - Multi-provider speech-to-text support.

This module provides a clean abstraction layer for different STT providers,
enabling easy switching between providers and fallback mechanisms.

Architecture follows the pattern established in:
- llm_processor.py (fallback mechanism)
- context_detector.py (ABC + factory pattern)

Supported providers:
- Gladia: Primary provider with streaming and native translation
- ElevenLabs: Fallback provider with batch transcription
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING, Callable, Generator

if TYPE_CHECKING:
    pass


class STTCapability(Enum):
    """Capabilities that STT providers may support.

    Used for feature detection and fallback logic.
    """

    BATCH = auto()  # Upload complete audio file for transcription
    STREAMING = auto()  # Real-time WebSocket streaming during recording
    TRANSLATION = auto()  # Built-in translation (no separate LLM call needed)
    DIARIZATION = auto()  # Speaker identification
    WORD_TIMESTAMPS = auto()  # Per-word timing information


@dataclass
class WordInfo:
    """Information about a single word in transcription.

    Attributes:
        word: The transcribed word
        start: Start time in seconds
        end: End time in seconds
        confidence: Word-level confidence score (0.0-1.0)
    """

    word: str
    start: float
    end: float
    confidence: float | None = None


@dataclass
class TranscriptionResult:
    """Result from STT transcription.

    Attributes:
        text: The transcribed text
        language: Detected or specified language code (e.g., "en", "fr")
        confidence: Overall confidence score (0.0-1.0)
        is_final: True if this is the final result (False for streaming partials)
        words: Optional word-level details with timestamps
        translation: Optional translated text (if provider supports native translation)
        raw_response: Provider-specific raw response data for debugging
    """

    text: str
    language: str | None = None
    confidence: float | None = None
    is_final: bool = True
    words: list[WordInfo] | None = None
    translation: str | None = None
    raw_response: dict = field(default_factory=dict)


@dataclass
class STTProviderConfig:
    """Configuration for an STT provider.

    Attributes:
        api_key: API key for authentication
        model: Model identifier (provider-specific, e.g., "scribe_v1" for ElevenLabs)
        timeout: Request timeout in seconds
        language: Language code hint (None for auto-detect)
        sample_rate: Audio sample rate in Hz (default: 16000)
        extra: Provider-specific configuration options
    """

    api_key: str
    model: str = ""
    timeout: float = 120.0
    language: str | None = None
    sample_rate: int = 16000
    extra: dict = field(default_factory=dict)


class STTProvider(ABC):
    """Abstract base class for STT providers.

    Implementations should support at minimum batch transcription.
    Streaming and translation support is optional and indicated via capabilities.

    Usage:
        provider = get_stt_provider("gladia")
        if provider.is_available():
            result = provider.transcribe(audio_bytes)
            print(result.text)
    """

    def __init__(self, config: STTProviderConfig):
        """Initialize the provider with configuration.

        Args:
            config: Provider configuration including API key and settings
        """
        self.config = config
        self._client = None

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable provider name (e.g., 'Gladia', 'ElevenLabs')."""
        pass

    @property
    @abstractmethod
    def capabilities(self) -> set[STTCapability]:
        """Set of capabilities this provider supports."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this provider is properly configured and available.

        Returns:
            True if provider can be used (API key set, SDK available)
        """
        pass

    @abstractmethod
    def transcribe(self, audio_data: bytes, audio_format: str = "wav") -> TranscriptionResult | None:
        """Transcribe audio data in batch mode.

        Args:
            audio_data: Raw audio bytes (WAV format by default)
            audio_format: Audio format identifier ("wav", "mp3", "webm", etc.)

        Returns:
            TranscriptionResult with text and metadata, or None on failure
        """
        pass

    def supports_streaming(self) -> bool:
        """Check if provider supports real-time streaming.

        Returns:
            True if STREAMING capability is present
        """
        return STTCapability.STREAMING in self.capabilities

    def supports_translation(self) -> bool:
        """Check if provider supports native translation.

        Returns:
            True if TRANSLATION capability is present
        """
        return STTCapability.TRANSLATION in self.capabilities

    def stream_transcribe(
        self,
        audio_generator: Generator[bytes, None, None],
        on_partial: Callable[[TranscriptionResult], None] | None = None,
    ) -> TranscriptionResult | None:
        """Stream audio for real-time transcription.

        Override in providers that support streaming (Gladia).
        This method should be called at the START of recording, sending
        audio chunks as they are captured for near-zero perceived latency.

        Args:
            audio_generator: Generator yielding audio chunks as they're recorded
            on_partial: Callback for partial (interim) results during transcription

        Returns:
            Final TranscriptionResult when streaming ends, or None on failure

        Raises:
            NotImplementedError: If provider doesn't support streaming
        """
        raise NotImplementedError(f"{self.name} does not support streaming transcription")

    def translate(
        self,
        audio_data: bytes,
        target_language: str = "en",
        audio_format: str = "wav",
    ) -> TranscriptionResult | None:
        """Transcribe and translate audio in one operation.

        Uses native provider translation when available (Gladia).
        Override in providers that support translation.

        Args:
            audio_data: Raw audio bytes
            target_language: Target language code (e.g., "en", "fr")
            audio_format: Audio format identifier

        Returns:
            TranscriptionResult with both text (original) and translation

        Raises:
            NotImplementedError: If provider doesn't support native translation
        """
        raise NotImplementedError(f"{self.name} does not support native translation")


class NullSTTProvider(STTProvider):
    """Null implementation for when no provider is available.

    Used for graceful degradation when:
    - No API key is configured
    - Required SDK is not installed
    - All providers fail

    Always returns None/empty results without errors.
    """

    def __init__(self):
        """Initialize null provider with empty config."""
        super().__init__(STTProviderConfig(api_key=""))

    @property
    def name(self) -> str:
        """Return provider name."""
        return "None"

    @property
    def capabilities(self) -> set[STTCapability]:
        """Return empty capabilities set."""
        return set()

    def is_available(self) -> bool:
        """Null provider is never available."""
        return False

    def transcribe(self, audio_data: bytes, audio_format: str = "wav") -> TranscriptionResult | None:
        """Return None (no transcription possible)."""
        return None
