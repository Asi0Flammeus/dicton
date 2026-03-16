"""Speech recognition - STT provider abstraction (capture then transcribe) - Cross-platform"""

import contextlib
import io
import os
import wave

import numpy as np

from ...shared.platform_utils import IS_LINUX, IS_WINDOWS
from ..stt.factory import get_stt_provider_with_fallback
from ..stt.provider import NullSTTProvider, STTProvider


# Suppress audio system warnings (ALSA on Linux, etc.)
@contextlib.contextmanager
def suppress_stderr():
    """Suppress stderr to hide audio system warnings."""
    try:
        devnull = os.open(os.devnull, os.O_WRONLY)
        old_stderr = os.dup(2)
        try:
            os.dup2(devnull, 2)
            yield
        finally:
            os.dup2(old_stderr, 2)
            os.close(devnull)
            os.close(old_stderr)
    except Exception:
        # On some platforms this may fail, just yield without suppression
        yield


with suppress_stderr():
    import pyaudio

from ...shared.config import config
from ...shared.text_processor import get_text_processor

# Import visualizer based on configured backend
if config.VISUALIZER_BACKEND == "gtk":
    try:
        from ..ui.visualizer_gtk import get_visualizer
    except ImportError as e:
        print(f"⚠ GTK not available ({e}), falling back to pygame")
        from ..ui.visualizer import get_visualizer
elif config.VISUALIZER_BACKEND == "vispy":
    try:
        from ..ui.visualizer_vispy import get_visualizer
    except ImportError:
        print("⚠ VisPy not available, falling back to pygame")
        from ..ui.visualizer import get_visualizer
else:
    from ..ui.visualizer import get_visualizer


class SpeechRecognizer:
    """Speech recognizer: record audio, then transcribe via STT provider."""

    def __init__(self):
        self.recording = False
        self._cancelled = False  # Flag for immediate cancel (discard audio)
        self.input_device = None

        # Initialize STT provider via factory (respects STT_PROVIDER config)
        self._stt_provider: STTProvider = get_stt_provider_with_fallback()
        self._provider_available = not isinstance(self._stt_provider, NullSTTProvider)

        with suppress_stderr():
            self.audio = pyaudio.PyAudio()

        self._find_input_device()

        # Provider status is printed by the factory (verbose=True by default)
        if not self._provider_available:
            print("   Set MISTRAL_API_KEY or ELEVENLABS_API_KEY in .env")

    @property
    def provider_name(self) -> str:
        """Get the name of the active STT provider."""
        return self._stt_provider.name if self._provider_available else "None"

    # Legacy property for backwards compatibility
    @property
    def use_elevenlabs(self) -> bool:
        """Check if any STT provider is available (legacy compatibility)."""
        return self._provider_available

    @property
    def stt_provider(self) -> STTProvider:
        """Expose underlying STT provider for direct use (e.g., chunked pipeline)."""
        return self._stt_provider

    def _find_input_device(self):
        """Find the best available input device - cross-platform."""
        self.device_sample_rate = config.SAMPLE_RATE

        try:
            if config.MIC_DEVICE != "auto":
                try:
                    self.input_device = int(config.MIC_DEVICE)
                    info = self.audio.get_device_info_by_index(self.input_device)
                    self.device_sample_rate = int(info["defaultSampleRate"])
                    print(f"✓ Mic: {info['name']} @ {self.device_sample_rate}Hz (forced)")
                    return
                except Exception:
                    print(f"⚠ Device {config.MIC_DEVICE} not found, auto-detecting...")

            default_info = self.audio.get_default_input_device_info()
            default_idx = default_info["index"]

            devices = []
            for i in range(self.audio.get_device_count()):
                try:
                    info = self.audio.get_device_info_by_index(i)
                    if info["maxInputChannels"] > 0:
                        devices.append(
                            {
                                "index": i,
                                "name": info["name"],
                                "rate": int(info["defaultSampleRate"]),
                                "is_default": i == default_idx,
                            }
                        )
                except Exception:
                    continue

            if not devices:
                print("⚠ No input devices found")
                return

            # Platform-specific device selection
            selected = self._select_best_device(devices)

            self.input_device = selected["index"]
            self.device_sample_rate = selected["rate"]
            print(f"✓ Mic: {selected['name']}")

        except Exception as e:
            print(f"⚠ Could not detect mic: {e}")
            self.input_device = None
            self.device_sample_rate = config.SAMPLE_RATE

    def _select_best_device(self, devices: list) -> dict:
        """Select the best audio input device based on platform."""
        selected = None

        if IS_LINUX:
            # Linux: prefer PulseAudio, then default
            for d in devices:
                if d["name"].lower() == "pulse":
                    selected = d
                    break

        elif IS_WINDOWS:
            # Windows: prefer default device, or one with "microphone" in name
            for d in devices:
                if d["is_default"]:
                    selected = d
                    break
            if not selected:
                for d in devices:
                    if "microphone" in d["name"].lower():
                        selected = d
                        break

        # Fallback: use default device or first available
        if not selected:
            for d in devices:
                if d["is_default"]:
                    selected = d
                    break
        if not selected:
            selected = devices[0]

        return selected

    def record(self, on_chunk=None) -> np.ndarray | None:
        """Record audio until stopped, with visualizer feedback.

        Note: After recording stops, the visualizer switches to processing mode
        (pulsing animation) instead of stopping. The caller is responsible for
        calling viz.stop() after processing is complete.
        """
        if not self._provider_available:
            print("⚠ No STT provider available")
            return None

        viz = get_visualizer()
        stream = None
        frames = []
        self._cancelled = False  # Reset cancel flag

        try:
            with suppress_stderr():
                stream = self.audio.open(
                    format=pyaudio.paInt16,
                    channels=1,
                    rate=config.SAMPLE_RATE,
                    input=True,
                    input_device_index=self.input_device,
                    frames_per_buffer=config.CHUNK_SIZE,
                )

            self.recording = True
            viz.start()
            print("🎤 Recording...")

            while self.recording:
                try:
                    data = stream.read(config.CHUNK_SIZE, exception_on_overflow=False)
                    frames.append(data)
                    viz.update(data)
                    if on_chunk:
                        on_chunk(data)
                except Exception as e:
                    if config.DEBUG:
                        print(f"⚠ Read error: {e}")
                    break

        except Exception as e:
            print(f"❌ Recording error: {e}")
            viz.stop()  # Stop visualizer on error
            return None

        finally:
            self.recording = False
            if stream:
                stream.stop_stream()
                stream.close()

        # Check if recording was cancelled (tap detected)
        if self._cancelled:
            viz.stop()  # Stop visualizer on cancel
            return None

        if not frames:
            viz.stop()  # Stop visualizer if no frames
            return None

        # Switch visualizer to processing mode (pulsing animation)
        # Caller will call viz.stop() after transcription/LLM processing completes
        viz.start_processing()

        # Convert to numpy array
        audio_data = b"".join(frames)
        audio_array = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0

        return audio_array

    def stop(self):
        """Stop recording (will process audio)."""
        self.recording = False

    def record_for_duration(self, duration_seconds: float) -> np.ndarray | None:
        """Record audio for a fixed duration (for latency testing)."""
        if not self._provider_available:
            print("⚠ No STT provider available")
            return None

        stream = None
        frames = []

        try:
            with suppress_stderr():
                stream = self.audio.open(
                    format=pyaudio.paInt16,
                    channels=1,
                    rate=config.SAMPLE_RATE,
                    input=True,
                    input_device_index=self.input_device,
                    frames_per_buffer=config.CHUNK_SIZE,
                )

            # Calculate number of chunks needed
            chunks_needed = int(duration_seconds * config.SAMPLE_RATE / config.CHUNK_SIZE)

            for _ in range(chunks_needed):
                try:
                    data = stream.read(config.CHUNK_SIZE, exception_on_overflow=False)
                    frames.append(data)
                except Exception as e:
                    if config.DEBUG:
                        print(f"⚠ Read error: {e}")
                    break

        except Exception as e:
            print(f"❌ Recording error: {e}")
            return None

        finally:
            if stream:
                stream.stop_stream()
                stream.close()

        if not frames:
            return None

        # Convert to numpy array
        audio_data = b"".join(frames)
        audio_array = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0

        return audio_array

    def cancel(self):
        """Cancel recording (discard audio, tap detected)."""
        self._cancelled = True
        self.recording = False

    def _audio_to_wav(self, audio: np.ndarray) -> bytes:
        """Convert numpy float32 audio array to WAV bytes.

        Args:
            audio: Float32 audio array normalized to [-1.0, 1.0].

        Returns:
            WAV file as bytes.
        """
        # Convert float32 audio to int16 bytes
        audio_int16 = (audio * 32767).astype(np.int16)

        # Create WAV in memory
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(config.SAMPLE_RATE)
            wav_file.writeframes(audio_int16.tobytes())

        wav_buffer.seek(0)
        return wav_buffer.read()

    def transcribe(self, audio: np.ndarray) -> str | None:
        """Transcribe recorded audio using the configured STT provider."""
        if audio is None or len(audio) == 0:
            return None

        if not self._provider_available:
            print("⚠ No STT provider available")
            return None

        try:
            # Convert numpy array to WAV bytes
            wav_bytes = self._audio_to_wav(audio)

            # Use provider abstraction
            result = self._stt_provider.transcribe(wav_bytes)

            if result and result.text:
                return self._filter(result.text)
            return None

        except Exception as e:
            print(f"❌ Transcription error: {e}")
            if config.DEBUG:
                import traceback

                traceback.print_exc()
            return None

    def _filter(self, text: str) -> str | None:
        """Filter out noise, apply custom dictionary, and clean up text."""
        if not text or len(text) < 3:
            return None

        lower = text.lower().strip()

        # Common noise phrases
        noise = {
            "thanks for watching",
            "thank you for watching",
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
        }
        if lower in noise:
            return None

        # Single short words are usually noise
        if len(text.split()) == 1 and len(text) < 10:
            return None

        # Apply custom dictionary replacements
        processor = get_text_processor()
        text = processor.process(text)

        return text

    def filter_text(self, text: str) -> str | None:
        """Apply noise filtering and dictionary to externally-provided text."""
        return self._filter(text)

    def cleanup(self):
        """Cleanup resources."""
        self.audio.terminate()
