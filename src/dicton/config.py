"""Configuration for Dicton"""

import os
from pathlib import Path

from dotenv import load_dotenv


def _load_env_files():
    """Load .env from multiple possible locations (first found wins).

    Priority order:
    1. User config dir (~/.config/dicton/) - where dashboard saves settings
    2. Current working directory - for development
    3. System install (/opt/dicton/) - read-only defaults
    """
    locations = [
        Path.home() / ".config" / "dicton" / ".env",  # User config dir - FIRST!
        Path.cwd() / ".env",  # Current working directory
        Path("/opt/dicton/.env"),  # System install (read-only fallback)
    ]

    for env_path in locations:
        if env_path.exists():
            load_dotenv(env_path)
            return str(env_path)

    # Fallback: let dotenv search normally
    load_dotenv()
    return None


_loaded_env = _load_env_files()

# Flexoki color palette - https://github.com/kepano/flexoki
FLEXOKI_COLORS = {
    # Dark accent colors (600 values) - main colors
    "red": {
        "main": (175, 48, 41),
        "mid": (140, 38, 33),
        "dim": (90, 25, 21),
        "glow": (209, 77, 65),
    },
    "orange": {
        "main": (188, 82, 21),
        "mid": (150, 65, 17),
        "dim": (95, 42, 11),
        "glow": (218, 112, 44),
    },
    "yellow": {
        "main": (173, 131, 1),
        "mid": (138, 105, 1),
        "dim": (87, 66, 1),
        "glow": (208, 162, 21),
    },
    "green": {
        "main": (102, 128, 11),
        "mid": (82, 102, 9),
        "dim": (51, 64, 6),
        "glow": (135, 154, 57),
    },
    "cyan": {
        "main": (36, 131, 123),
        "mid": (29, 105, 98),
        "dim": (18, 66, 62),
        "glow": (58, 169, 159),
    },
    "blue": {
        "main": (32, 94, 166),
        "mid": (26, 75, 133),
        "dim": (16, 47, 83),
        "glow": (67, 133, 190),
    },
    "purple": {
        "main": (94, 64, 157),
        "mid": (75, 51, 126),
        "dim": (47, 32, 79),
        "glow": (139, 126, 200),
    },
    "magenta": {
        "main": (160, 47, 111),
        "mid": (128, 38, 89),
        "dim": (80, 24, 56),
        "glow": (206, 93, 151),
    },
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
    "center-upper": lambda w, h, size: ((w - size) // 2, h // 3 - size // 2),
}


class Config:
    """Configuration for Dicton"""

    # Paths - use user-writable directories
    CONFIG_DIR = Path.home() / ".config" / "dicton"
    DATA_DIR = Path.home() / ".local" / "share" / "dicton"
    MODELS_DIR = DATA_DIR / "models"

    # ElevenLabs API
    ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")

    # LLM Provider selection: "gemini" or "anthropic"
    # The primary provider will be used first, with fallback to the other if available
    LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini").lower()

    # Gemini API (for Act on Text, reformulation, translation)
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")

    # Anthropic API (alternative for Act on Text, reformulation, translation)
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
    ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")

    # ElevenLabs STT model
    ELEVENLABS_MODEL = os.getenv("ELEVENLABS_MODEL", "scribe_v1")

    # API timeout in seconds (prevents infinite hang if VPN blocks APIs)
    API_TIMEOUT = float(os.getenv("API_TIMEOUT", "30"))

    # STT timeout in seconds (longer for ElevenLabs processing large audio files)
    # Rule of thumb: ~10s per minute of audio + 30s base
    STT_TIMEOUT = float(os.getenv("STT_TIMEOUT", "120"))

    # Hotkey (legacy modifier+key style)
    HOTKEY_MODIFIER = os.getenv("HOTKEY_MODIFIER", "alt")
    HOTKEY_KEY = os.getenv("HOTKEY_KEY", "g")

    # FN Key hotkey settings (new Phase 1 system)
    # HOTKEY_BASE: "fn" for FN key (XF86WakeUp), or "custom" for modifier+key combo
    HOTKEY_BASE = os.getenv("HOTKEY_BASE", "fn")
    # Custom hotkey value: modifier+key combo (e.g., "alt+g", "ctrl+shift+d")
    # Only used when HOTKEY_BASE is "custom"
    CUSTOM_HOTKEY_VALUE = os.getenv("CUSTOM_HOTKEY_VALUE", "alt+g")
    # Hold threshold in ms - press longer than this triggers push-to-talk
    # Lower = more responsive PTT, higher = better tap detection
    HOTKEY_HOLD_THRESHOLD_MS = int(os.getenv("HOTKEY_HOLD_THRESHOLD_MS", "100"))
    # Double-tap window in ms - second press within this triggers toggle mode
    HOTKEY_DOUBLE_TAP_WINDOW_MS = int(os.getenv("HOTKEY_DOUBLE_TAP_WINDOW_MS", "300"))
    # Activation delay in ms - wait before starting recording to distinguish from double-tap
    HOTKEY_ACTIVATION_DELAY_MS = int(os.getenv("HOTKEY_ACTIVATION_DELAY_MS", "50"))

    # Secondary hotkeys - alternative keys that work like FN (for keyboards without KEY_WAKEUP)
    # Options: escape, f1-f12, capslock, pause, insert, home, end, pageup, pagedown, none
    SECONDARY_HOTKEY = os.getenv("SECONDARY_HOTKEY", "none").lower()  # Basic/Reformulation mode
    SECONDARY_HOTKEY_TRANSLATION = os.getenv("SECONDARY_HOTKEY_TRANSLATION", "none").lower()  # Translation mode
    SECONDARY_HOTKEY_ACT_ON_TEXT = os.getenv("SECONDARY_HOTKEY_ACT_ON_TEXT", "none").lower()  # Act on Text mode

    # Visualizer theme color (red, orange, yellow, green, cyan, blue, purple, magenta)
    THEME_COLOR = os.getenv("THEME_COLOR", "orange").lower()

    # Animation position (top-right, top-left, bottom-right, bottom-left, center)
    ANIMATION_POSITION = os.getenv("ANIMATION_POSITION", "top-right").lower()

    # Visualizer style (minimalistic, classic, legacy, toric, terminal)
    VISUALIZER_STYLE = os.getenv("VISUALIZER_STYLE", "toric").lower()

    # Visualizer backend (pygame, vispy, gtk)
    # - pygame: Default, works everywhere, window opacity on Linux
    # - vispy: OpenGL-based, requires vispy + pyglet
    # - gtk: GTK3/Cairo, true per-pixel transparency on Linux (requires PyGObject)
    VISUALIZER_BACKEND = os.getenv("VISUALIZER_BACKEND", "pygame").lower()

    # Visualizer window opacity for Linux (0.0-1.0, requires compositor)
    # Lower values = more transparent. Default 0.85 for visible ring with subtle background
    VISUALIZER_OPACITY = float(os.getenv("VISUALIZER_OPACITY", "0.85"))

    # Audio settings
    SAMPLE_RATE = 16000
    CHUNK_SIZE = 1024

    # Set to device index number to force specific mic, or "auto"
    MIC_DEVICE = os.getenv("MIC_DEVICE", "auto")

    # Language: "auto" (None), "en", "fr", etc. (ISO-639-1 or ISO-639-3)
    LANGUAGE = os.getenv("LANGUAGE", "auto")

    # Filler word filtering: "true" to enable removal of filler words (um, uh, like, etc.)
    FILTER_FILLERS = os.getenv("FILTER_FILLERS", "true").lower() == "true"

    # LLM-based reformulation: "true" to enable light reformulation via configured LLM_PROVIDER
    # When enabled, uses LLM for smarter cleanup. When disabled, uses local filler removal only.
    ENABLE_REFORMULATION = os.getenv("ENABLE_REFORMULATION", "true").lower() == "true"

    # Paste threshold: texts with more words than this will use clipboard paste
    # instead of character-by-character streaming (faster for long dictations)
    # Set to 0 to always use streaming, or -1 to always use paste
    PASTE_THRESHOLD_WORDS = int(os.getenv("PASTE_THRESHOLD_WORDS", "10"))

    DEBUG = os.getenv("DEBUG", "false").lower() == "true"

    # Context detection - adapts LLM prompts and typing speed based on active app
    CONTEXT_ENABLED = os.getenv("CONTEXT_ENABLED", "true").lower() == "true"

    # Context detection debug mode - logs detected context and matched profiles
    CONTEXT_DEBUG = os.getenv("CONTEXT_DEBUG", "false").lower() == "true"

    @classmethod
    def create_dirs(cls):
        """Create required directories in user-writable locations."""
        cls.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        cls.DATA_DIR.mkdir(parents=True, exist_ok=True)
        cls.MODELS_DIR.mkdir(parents=True, exist_ok=True)

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
