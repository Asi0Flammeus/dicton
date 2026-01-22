"""STT Provider Interface for Dicton

Provides a unified interface for Speech-to-Text providers with support for
batch transcription, streaming, and translation capabilities.

Architecture: Provider abstraction with fallback chain:
  - Each provider implements specific capabilities
  - Factory provides the best available provider
  - Graceful degradation when providers unavailable
"""

import io
import logging
import wave
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from enum import Enum, auto

logger = logging.getLogger(__name__)


class STTCapability(Enum):
    """Capabilities supported by STT providers."""

    BATCH = auto()  # Batch transcription (upload audio, get text)
    STREAMING = auto()  # Real-time streaming transcription
    TRANSLATION = auto()  # Native translation support
    DIARIZATION = auto()  # Speaker diarization
    WORD_TIMESTAMPS = auto()  # Word-level timing information


@dataclass
class WordInfo:
    """Word-level transcription information.

    Attributes:
        word: The transcribed word
        start: Start time in seconds
        end: End time in seconds
        confidence: Confidence score (0.0-1.0)
    """

    word: str
    start: float
    end: float
    confidence: float = 1.0


@dataclass
class TranscriptionResult:
    """Result from a transcription request.

    Attributes:
        text: The transcribed text
        language: Detected or specified language code (e.g., "en", "fr")
        confidence: Overall confidence score (0.0-1.0)
        is_final: Whether this is a final result (vs. partial in streaming)
        words: Optional word-level timing information
        duration: Audio duration in seconds
    """

    text: str
    language: str = ""
    confidence: float = 1.0
    is_final: bool = True
    words: list[WordInfo] = field(default_factory=list)
    duration: float = 0.0


@dataclass
class STTProviderConfig:
    """Configuration for STT providers.

    Attributes:
        api_key: API key for the provider
        model: Model identifier (provider-specific)
        timeout: Request timeout in seconds
        language: Optional language hint (e.g., "en", "fr")
        sample_rate: Audio sample rate in Hz
    """

    api_key: str = ""
    model: str = ""
    timeout: float = 30.0
    language: str = ""
    sample_rate: int = 16000


class STTProvider(ABC):
    """Abstract base class for STT providers.

    Providers should implement the capabilities they support and return
    None or raise appropriate exceptions for unsupported operations.
    """

    def __init__(self, config: STTProviderConfig | None = None):
        """Initialize the provider with optional configuration.

        Args:
            config: Provider configuration. If None, uses defaults.
        """
        self._config = config or STTProviderConfig()

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name of the provider."""
        pass

    @property
    @abstractmethod
    def capabilities(self) -> set[STTCapability]:
        """Set of capabilities this provider supports."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the provider is available and configured.

        Returns:
            True if provider has required credentials and dependencies.
        """
        pass

    def has_capability(self, capability: STTCapability) -> bool:
        """Check if provider supports a specific capability.

        Args:
            capability: The capability to check.

        Returns:
            True if the capability is supported.
        """
        return capability in self.capabilities

    @property
    def max_audio_duration(self) -> int | None:
        """Maximum audio duration in seconds, or None for no limit."""
        return None

    @property
    def max_audio_size(self) -> int | None:
        """Maximum audio size in bytes, or None for no limit."""
        return None

    def _validate_audio(self, audio_data: bytes) -> bool:
        """Validate audio data against provider limits.

        Checks audio size and duration against provider-specific limits.

        Args:
            audio_data: Audio data as bytes.

        Returns:
            True if audio is valid, False otherwise.
        """
        # Check size limit
        if self.max_audio_size is not None and len(audio_data) > self.max_audio_size:
            logger.error(
                f"{self.name}: Audio size {len(audio_data)} bytes exceeds "
                f"limit of {self.max_audio_size} bytes"
            )
            return False

        # Check duration limit (only for WAV files we can parse)
        if self.max_audio_duration is not None and audio_data[:4] == b"RIFF":
            try:
                wav_buffer = io.BytesIO(audio_data)
                with wave.open(wav_buffer, "rb") as wav:
                    frames = wav.getnframes()
                    rate = wav.getframerate()
                    duration = frames / rate
                    if duration > self.max_audio_duration:
                        logger.error(
                            f"{self.name}: Audio duration {duration:.1f}s exceeds "
                            f"limit of {self.max_audio_duration}s"
                        )
                        return False
            except Exception as e:
                logger.debug(f"Could not parse WAV for duration check: {e}")
                # Allow through - API will reject if invalid

        return True

    @abstractmethod
    def transcribe(self, audio_data: bytes) -> TranscriptionResult | None:
        """Transcribe audio data (batch mode).

        Args:
            audio_data: Audio data as bytes (typically WAV format).

        Returns:
            TranscriptionResult on success, None on failure.
        """
        pass

    def stream_transcribe(
        self,
        audio_generator: Iterator[bytes],
        on_partial: Callable[[TranscriptionResult], None] | None = None,
    ) -> TranscriptionResult | None:
        """Transcribe audio stream in real-time.

        Default implementation falls back to batch mode by collecting
        all audio chunks and calling transcribe().

        Args:
            audio_generator: Iterator yielding audio chunks.
            on_partial: Optional callback for partial results.

        Returns:
            Final TranscriptionResult on success, None on failure.
        """
        if not self.has_capability(STTCapability.STREAMING):
            # Fallback to batch mode
            chunks = list(audio_generator)
            if not chunks:
                return None
            audio_data = b"".join(chunks)
            return self.transcribe(audio_data)
        return None

    def translate(
        self, audio_data: bytes, target_language: str = "en"
    ) -> TranscriptionResult | None:
        """Transcribe and translate audio to target language.

        Default implementation returns None (unsupported).

        Args:
            audio_data: Audio data as bytes.
            target_language: Target language code (e.g., "en", "fr").

        Returns:
            TranscriptionResult with translated text, or None if unsupported.
        """
        if not self.has_capability(STTCapability.TRANSLATION):
            return None
        return None

    def _convert_to_wav(self, audio_data: bytes) -> io.BytesIO | None:
        """Convert audio data to WAV format if needed.

        Assumes input is either:
        - Raw PCM int16 samples at configured sample rate
        - Already a WAV file

        Args:
            audio_data: Audio data as bytes.

        Returns:
            BytesIO containing WAV data, or None on error.
        """
        # Check if already WAV format (starts with RIFF header)
        if audio_data[:4] == b"RIFF":
            return io.BytesIO(audio_data)

        # Assume raw PCM int16, convert to WAV
        try:
            wav_buffer = io.BytesIO()
            with wave.open(wav_buffer, "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)  # 16-bit
                wav_file.setframerate(self._config.sample_rate)
                wav_file.writeframes(audio_data)
            wav_buffer.seek(0)
            return wav_buffer
        except Exception as e:
            logger.error(f"Failed to convert audio to WAV: {e}")
            return None


class NullSTTProvider(STTProvider):
    """Null implementation for graceful degradation.

    Used when no STT provider is available. All operations return None
    but don't raise exceptions.
    """

    @property
    def name(self) -> str:
        return "None"

    @property
    def capabilities(self) -> set[STTCapability]:
        return set()

    def is_available(self) -> bool:
        return True  # Always "available" as a fallback

    def transcribe(self, audio_data: bytes) -> TranscriptionResult | None:
        return None

    def stream_transcribe(
        self,
        audio_generator: Iterator[bytes],
        on_partial: Callable[[TranscriptionResult], None] | None = None,
    ) -> TranscriptionResult | None:
        return None

    def translate(
        self, audio_data: bytes, target_language: str = "en"
    ) -> TranscriptionResult | None:
        return None
