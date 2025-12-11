"""Speech recognition - Online API with local fallback"""
import os
import sys
import wave
import io
import numpy as np
import contextlib

# Suppress ALSA warnings
@contextlib.contextmanager
def suppress_stderr():
    devnull = os.open(os.devnull, os.O_WRONLY)
    old_stderr = os.dup(2)
    try:
        os.dup2(devnull, 2)
        yield
    finally:
        os.dup2(old_stderr, 2)
        os.close(devnull)
        os.close(old_stderr)

with suppress_stderr():
    import pyaudio

from config import config
from visualizer import get_visualizer

# Try imports
try:
    from openai import OpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

try:
    from faster_whisper import WhisperModel
    HAS_WHISPER = True
except ImportError:
    HAS_WHISPER = False


class SpeechRecognizer:
    """Simple speech recognizer: online API first, local fallback"""

    def __init__(self):
        self.client = None
        self.local_model = None
        self.use_online = False
        self.recording = False
        self.input_device = None

        with suppress_stderr():
            self.audio = pyaudio.PyAudio()

        # Find best input device
        self._find_input_device()

        # Try online API first
        if HAS_OPENAI and config.OPENAI_API_KEY:
            try:
                self.client = OpenAI(api_key=config.OPENAI_API_KEY)
                self.use_online = True
                print("✓ Using OpenAI API (fast)")
            except Exception as e:
                print(f"API init failed: {e}")

        # Load local model as fallback
        if not self.use_online and HAS_WHISPER:
            self._load_local_model()

    def _find_input_device(self):
        """Find the best available input device"""
        self.device_sample_rate = config.SAMPLE_RATE  # Default

        try:
            # Check if user specified a device
            if config.MIC_DEVICE != "auto":
                try:
                    self.input_device = int(config.MIC_DEVICE)
                    info = self.audio.get_device_info_by_index(self.input_device)
                    self.device_sample_rate = int(info['defaultSampleRate'])
                    print(f"✓ Mic: {info['name']} @ {self.device_sample_rate}Hz (forced)")
                    return
                except Exception:
                    print(f"⚠ Device {config.MIC_DEVICE} not found, auto-detecting...")

            # Get default input device first
            default_info = self.audio.get_default_input_device_info()
            default_idx = default_info['index']

            # List all input devices
            devices = []
            for i in range(self.audio.get_device_count()):
                try:
                    info = self.audio.get_device_info_by_index(i)
                    if info['maxInputChannels'] > 0:
                        devices.append({
                            'index': i,
                            'name': info['name'],
                            'channels': info['maxInputChannels'],
                            'rate': int(info['defaultSampleRate']),
                            'is_default': i == default_idx
                        })
                except Exception:
                    continue

            if not devices:
                print("⚠ No input devices found")
                return

            # Prefer pulse/default for compatibility, then hardware
            selected = None

            # Priority 1: Pulse audio (handles resampling automatically)
            for d in devices:
                if d['name'].lower() == 'pulse':
                    selected = d
                    break

            # Priority 2: System default
            if not selected:
                for d in devices:
                    if d['is_default']:
                        selected = d
                        break

            # Priority 3: Hardware device with mic/analog in name
            if not selected:
                for d in devices:
                    name_lower = d['name'].lower()
                    if 'hw:' in name_lower and any(kw in name_lower for kw in ['analog', 'mic', 'input']):
                        selected = d
                        break

            # Fallback to first device
            if not selected:
                selected = devices[0]

            self.input_device = selected['index']
            self.device_sample_rate = selected['rate']
            print(f"✓ Mic: {selected['name']}")

            if config.DEBUG:
                print("Available input devices:")
                for d in devices:
                    marker = "→" if d['index'] == self.input_device else " "
                    print(f"  {marker} [{d['index']}] {d['name']} ({d['rate']}Hz)")

        except Exception as e:
            print(f"⚠ Could not detect mic: {e}")
            self.input_device = None
            self.device_sample_rate = config.SAMPLE_RATE

    def _load_local_model(self):
        """Load local whisper model"""
        try:
            print(f"Loading local model ({config.WHISPER_MODEL})...")
            compute = "float16" if config.WHISPER_DEVICE == "cuda" else "int8"
            self.local_model = WhisperModel(
                config.WHISPER_MODEL,
                device=config.WHISPER_DEVICE,
                compute_type=compute,
                download_root=str(config.MODELS_DIR)
            )
            print(f"✓ Local model loaded ({config.WHISPER_DEVICE})")
        except Exception as e:
            print(f"Model load error: {e}")

    def record(self) -> np.ndarray | None:
        """Record audio until stopped"""
        stream = None
        viz = get_visualizer()
        try:
            # Use device's native sample rate
            sample_rate = self.device_sample_rate

            with suppress_stderr():
                stream = self.audio.open(
                    format=pyaudio.paInt16,
                    channels=1,
                    rate=sample_rate,
                    input=True,
                    input_device_index=self.input_device,
                    frames_per_buffer=config.CHUNK_SIZE
                )

            frames = []
            self.recording = True
            viz.start()

            print("🎤 Recording...")

            while self.recording:
                data = stream.read(config.CHUNK_SIZE, exception_on_overflow=False)
                frames.append(data)
                viz.update(data)

            if frames:
                audio = np.frombuffer(b''.join(frames), dtype=np.int16)
                audio_float = audio.astype(np.float32) / 32768.0

                # Debug: show audio stats
                duration = len(audio_float) / sample_rate
                level = np.max(np.abs(audio_float))
                print(f"📊 Audio: {duration:.1f}s, level={level:.4f}")

                # Resample to 16kHz if needed (Whisper expects 16kHz)
                if sample_rate != 16000:
                    audio_float = self._resample(audio_float, sample_rate, 16000)

                return audio_float
            return None

        except Exception as e:
            print(f"Record error: {e}")
            return None
        finally:
            self.recording = False
            viz.stop()
            if stream:
                stream.stop_stream()
                stream.close()

    def _resample(self, audio: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
        """Resample audio to target sample rate"""
        if orig_sr == target_sr:
            return audio

        # Simple linear interpolation resampling
        duration = len(audio) / orig_sr
        target_len = int(duration * target_sr)
        indices = np.linspace(0, len(audio) - 1, target_len)
        return np.interp(indices, np.arange(len(audio)), audio).astype(np.float32)

    def stop(self):
        """Stop recording"""
        self.recording = False

    def transcribe(self, audio: np.ndarray) -> str | None:
        """Transcribe audio data"""
        if audio is None:
            print("⚠ No audio data")
            return None

        duration = len(audio) / 16000  # After resampling
        level = np.max(np.abs(audio))
        print(f"📊 Transcribe input: {duration:.1f}s, level={level:.4f}, samples={len(audio)}")

        if len(audio) < 16000 * 0.3:
            print("⚠ Audio too short (<0.3s)")
            return None

        if level < 0.005:  # Lowered threshold
            print(f"⚠ Audio too quiet (level={level:.4f} < 0.005)")
            return None

        # Try online first
        if self.use_online:
            print("🌐 Sending to API...")
            result = self._transcribe_online(audio)
            if result:
                return result
            print("⚠ API returned no result")

        # Fallback to local
        if self.local_model:
            print("💻 Using local model...")
            return self._transcribe_local(audio)

        print("⚠ No transcription method available")
        return None

    def _transcribe_online(self, audio: np.ndarray) -> str | None:
        """Transcribe via OpenAI API"""
        try:
            # Convert to WAV at 16kHz (Whisper's expected rate)
            audio_int16 = (audio * 32767).astype(np.int16)
            buf = io.BytesIO()
            with wave.open(buf, 'wb') as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(16000)  # Always 16kHz after resampling
                w.writeframes(audio_int16.tobytes())
            buf.seek(0)
            buf.name = "audio.wav"

            # Language detection: don't pass language param to let Whisper auto-detect
            # The transcriptions endpoint should preserve original language
            params = {
                "model": "whisper-1",
                "file": buf,
                "response_format": "verbose_json"  # Get detected language info
            }

            # Only force language if explicitly set in config
            if config.LANGUAGE and config.LANGUAGE != "auto":
                lang = config.LANGUAGE.lower().split('_')[0][:2]
                params["language"] = lang

            response = self.client.audio.transcriptions.create(**params)

            # Extract text from verbose response
            if hasattr(response, 'text'):
                text = response.text.strip()
                if hasattr(response, 'language'):
                    print(f"🌍 Detected language: {response.language}")
            else:
                text = str(response).strip()

            print(f"📝 API raw result: '{text}'")
            filtered = self._filter(text)
            if filtered != text:
                print(f"📝 After filter: '{filtered}'")
            return filtered

        except Exception as e:
            print(f"❌ API error: {e}")
            return None

    def _transcribe_local(self, audio: np.ndarray) -> str | None:
        """Transcribe via local model"""
        try:
            lang = None if config.LANGUAGE == "auto" else config.LANGUAGE

            segments, _ = self.local_model.transcribe(
                audio,
                language=lang,
                beam_size=5,
                without_timestamps=True
            )

            parts = []
            for seg in segments:
                if seg.text and seg.text.strip():
                    parts.append(seg.text.strip())

            text = " ".join(parts).strip()
            return self._filter(text)

        except Exception as e:
            if config.DEBUG:
                print(f"Local error: {e}")
            return None

    def _filter(self, text: str) -> str | None:
        """Filter out noise and hallucinations"""
        if not text or len(text) < 3:
            return None

        lower = text.lower()
        noise = {
            "thanks for watching", "thank you for watching", "subscribe",
            "like and subscribe", "you", "thank you", "merci", "bye",
            "ok", "okay", "um", "uh", "ah", "oh", "hmm"
        }
        if lower in noise:
            return None

        # Single word often = noise
        if len(text.split()) == 1 and len(text) < 10:
            return None

        return text

    def cleanup(self):
        """Cleanup resources"""
        self.audio.terminate()
