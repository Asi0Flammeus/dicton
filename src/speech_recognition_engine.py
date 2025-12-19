"""Speech recognition - ElevenLabs STT (capture then transcribe) - Cross-platform"""
import os
import io
import wave
import contextlib

import numpy as np

from platform_utils import IS_LINUX, IS_WINDOWS


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

from config import config

# Import visualizer based on configured backend
if config.VISUALIZER_BACKEND == "vispy":
    try:
        from visualizer_vispy import get_visualizer
    except ImportError:
        print("⚠ VisPy not available, falling back to pygame")
        from visualizer import get_visualizer
else:
    from visualizer import get_visualizer

# Try ElevenLabs import
HAS_ELEVENLABS = False
try:
    from elevenlabs.client import ElevenLabs
    HAS_ELEVENLABS = True
except ImportError as e:
    print(f"ElevenLabs import error: {e}")


class SpeechRecognizer:
    """Speech recognizer: record audio, then transcribe via ElevenLabs."""

    def __init__(self):
        self.use_elevenlabs = False
        self.recording = False
        self.input_device = None
        self.client = None

        with suppress_stderr():
            self.audio = pyaudio.PyAudio()

        self._find_input_device()

        if HAS_ELEVENLABS and config.ELEVENLABS_API_KEY:
            self.use_elevenlabs = True
            self.client = ElevenLabs(api_key=config.ELEVENLABS_API_KEY)
            print(f"✓ Using ElevenLabs STT ({config.ELEVENLABS_MODEL})")
        elif not HAS_ELEVENLABS:
            print("⚠ ElevenLabs SDK not installed (pip install elevenlabs)")
        elif not config.ELEVENLABS_API_KEY:
            print("⚠ ELEVENLABS_API_KEY not set in .env")

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
                        devices.append({
                            "index": i,
                            "name": info["name"],
                            "rate": int(info["defaultSampleRate"]),
                            "is_default": i == default_idx,
                        })
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

    def record(self) -> np.ndarray | None:
        """Record audio until stopped, with visualizer feedback."""
        if not self.use_elevenlabs:
            print("⚠ ElevenLabs not available")
            return None

        viz = get_visualizer()
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

            self.recording = True
            viz.start()
            print("🎤 Recording...")

            while self.recording:
                try:
                    data = stream.read(config.CHUNK_SIZE, exception_on_overflow=False)
                    frames.append(data)
                    viz.update(data)
                except Exception as e:
                    if config.DEBUG:
                        print(f"⚠ Read error: {e}")
                    break

        except Exception as e:
            print(f"❌ Recording error: {e}")
            return None

        finally:
            self.recording = False
            viz.stop()
            if stream:
                stream.stop_stream()
                stream.close()

        if not frames:
            return None

        # Convert to numpy array
        audio_data = b"".join(frames)
        audio_array = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0

        return audio_array

    def stop(self):
        """Stop recording."""
        self.recording = False

    def transcribe(self, audio: np.ndarray) -> str | None:
        """Transcribe recorded audio using ElevenLabs STT."""
        if audio is None or len(audio) == 0:
            return None

        if not self.use_elevenlabs or not self.client:
            print("⚠ ElevenLabs not available")
            return None

        try:
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

            # Call ElevenLabs STT (language_code=None for auto-detect)
            transcription = self.client.speech_to_text.convert(
                file=wav_buffer,
                model_id=config.ELEVENLABS_MODEL,
            )

            # Extract text from response
            text = transcription.text if hasattr(transcription, "text") else str(transcription)

            if text:
                return self._filter(text)
            return None

        except Exception as e:
            print(f"❌ Transcription error: {e}")
            if config.DEBUG:
                import traceback
                traceback.print_exc()
            return None

    def _filter(self, text: str) -> str | None:
        """Filter out noise and common false positives."""
        if not text or len(text) < 3:
            return None

        lower = text.lower().strip()

        # Common noise phrases
        noise = {
            "thanks for watching", "thank you for watching", "subscribe",
            "you", "thank you", "merci", "bye", "ok", "okay", "um", "uh",
            "hmm", "huh", "ah", "oh", "eh",
        }
        if lower in noise:
            return None

        # Single short words are usually noise
        if len(text.split()) == 1 and len(text) < 10:
            return None

        return text

    def cleanup(self):
        """Cleanup resources."""
        self.audio.terminate()
