"""Configuration for Push-to-Write"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Configuration for Push-to-Write"""

    # Paths
    BASE_DIR = Path(__file__).parent.parent
    MODELS_DIR = BASE_DIR / "models"

    # ElevenLabs API
    ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")

    # ElevenLabs STT model
    ELEVENLABS_MODEL = os.getenv("ELEVENLABS_MODEL", "scribe_v1")

    # Local fallback model (only used if no API key)
    WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")
    WHISPER_DEVICE = "cuda" if os.getenv("USE_CUDA", "false").lower() == "true" else "cpu"

    # Hotkey
    HOTKEY_MODIFIER = os.getenv("HOTKEY_MODIFIER", "alt")
    HOTKEY_KEY = os.getenv("HOTKEY_KEY", "t")

    # Audio settings
    SAMPLE_RATE = 16000
    CHUNK_SIZE = 1024

    # Set to device index number to force specific mic, or "auto"
    MIC_DEVICE = os.getenv("MIC_DEVICE", "auto")

    # Language: "auto" (None), "en", "fr", etc. (ISO-639-1 or ISO-639-3)
    LANGUAGE = os.getenv("LANGUAGE", "auto")

    DEBUG = os.getenv("DEBUG", "false").lower() == "true"

    @classmethod
    def create_dirs(cls):
        cls.MODELS_DIR.mkdir(exist_ok=True)


config = Config()
