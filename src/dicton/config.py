"""Configuration for Push-to-Write"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Flexoki color palette - https://github.com/kepano/flexoki
FLEXOKI_COLORS = {
    # Dark accent colors (600 values) - main colors
    "red": {"main": (175, 48, 41), "mid": (140, 38, 33), "dim": (90, 25, 21), "glow": (209, 77, 65)},
    "orange": {"main": (188, 82, 21), "mid": (150, 65, 17), "dim": (95, 42, 11), "glow": (218, 112, 44)},
    "yellow": {"main": (173, 131, 1), "mid": (138, 105, 1), "dim": (87, 66, 1), "glow": (208, 162, 21)},
    "green": {"main": (102, 128, 11), "mid": (82, 102, 9), "dim": (51, 64, 6), "glow": (135, 154, 57)},
    "cyan": {"main": (36, 131, 123), "mid": (29, 105, 98), "dim": (18, 66, 62), "glow": (58, 169, 159)},
    "blue": {"main": (32, 94, 166), "mid": (26, 75, 133), "dim": (16, 47, 83), "glow": (67, 133, 190)},
    "purple": {"main": (94, 64, 157), "mid": (75, 51, 126), "dim": (47, 32, 79), "glow": (139, 126, 200)},
    "magenta": {"main": (160, 47, 111), "mid": (128, 38, 89), "dim": (80, 24, 56), "glow": (206, 93, 151)},
}

# Animation position options
POSITION_PRESETS = {
    "top-right": lambda w, h, size: (w - size - 10, 0),
    "top-left": lambda w, h, size: (20, 10),
    "top-center": lambda w, h, size: ((w - size) // 2, 10),
    "bottom-right": lambda w, h, size: (w - size - 20, h - size - 60),
    "bottom-left": lambda w, h, size: (20, h - size - 60),
    "bottom-center": lambda w, h, size: ((w - size) // 2, h - size - 60),
    "center": lambda w, h, size: ((w - size) // 2, (h - size) // 2),
}


class Config:
    """Configuration for Push-to-Write"""

    # Paths
    BASE_DIR = Path(__file__).parent.parent
    MODELS_DIR = BASE_DIR / "models"

    # ElevenLabs API
    ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")

    # ElevenLabs STT model
    ELEVENLABS_MODEL = os.getenv("ELEVENLABS_MODEL", "scribe_v1")

    # Hotkey
    HOTKEY_MODIFIER = os.getenv("HOTKEY_MODIFIER", "alt")
    HOTKEY_KEY = os.getenv("HOTKEY_KEY", "g")

    # Visualizer theme color (red, orange, yellow, green, cyan, blue, purple, magenta)
    THEME_COLOR = os.getenv("THEME_COLOR", "orange").lower()

    # Animation position (top-right, top-left, bottom-right, bottom-left, center)
    ANIMATION_POSITION = os.getenv("ANIMATION_POSITION", "top-right").lower()

    # Visualizer style (minimalistic, classic, legacy, toric, terminal)
    VISUALIZER_STYLE = os.getenv("VISUALIZER_STYLE", "toric").lower()

    # Visualizer backend (vispy, pygame)
    VISUALIZER_BACKEND = os.getenv("VISUALIZER_BACKEND", "pygame").lower()

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

    @classmethod
    def get_theme_colors(cls):
        """Get the color palette for the configured theme"""
        color_name = cls.THEME_COLOR
        if color_name not in FLEXOKI_COLORS:
            color_name = "orange"  # fallback
        return FLEXOKI_COLORS[color_name]

    @classmethod
    def get_animation_position(cls, screen_w: int, screen_h: int, size: int) -> tuple[int, int]:
        """Get the animation window position"""
        position = cls.ANIMATION_POSITION
        if position not in POSITION_PRESETS:
            position = "top-right"  # fallback
        return POSITION_PRESETS[position](screen_w, screen_h, size)


config = Config()
