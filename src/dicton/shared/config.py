"""Configuration for Dicton"""

import os
from pathlib import Path

from dotenv import dotenv_values, load_dotenv

from .app_paths import get_user_config_dir, get_user_data_dir, get_user_env_path

# Values to ignore when merging .env files — these are placeholders that the
# setup wizard or .env.example may have written and that must NOT mask a real
# value present in another .env file.
_PLACEHOLDER_VALUES = frozenset(
    {
        "",
        "test-key",
        "your-api-key",
        "your-key-here",
        "<paste-your-key>",
        "<your-key>",
        "changeme",
    }
)


def _is_placeholder(value: str | None) -> bool:
    if value is None:
        return True
    return value.strip().lower() in _PLACEHOLDER_VALUES


def _merge_env_file(env_path: Path, *, override: bool) -> bool:
    """Inject keys from ``env_path`` into ``os.environ``, skipping placeholders.

    - ``override=True``: a real (non-placeholder) value replaces an existing
      value, even if it's already a real value (config-UI semantics).
    - ``override=False``: only fills holes — keys absent or placeholder-valued
      in ``os.environ`` get filled.
    """
    if not env_path.exists():
        return False

    parsed = dotenv_values(env_path)
    for key, value in parsed.items():
        if _is_placeholder(value):
            continue
        if override or _is_placeholder(os.environ.get(key)):
            os.environ[key] = value  # type: ignore[assignment]
    return True


def _load_env_files():
    """Load .env files in cascade.

    Layered precedence (highest wins):
      1. ``DICTON_ENV_FILE`` (explicit override) — load only this, exit.
      2. ``~/.config/dicton/.env`` (where the dashboard saves) — high priority,
         but placeholder values do NOT win over later sources.
      3. ``$CWD/.env`` (development).
      4. ``~/.env`` (user-wide secrets — common pattern). Acts as a fallback
         filler so a placeholder in step 2 never masks a real key here.
      5. ``/opt/dicton/.env`` (system install read-only defaults).

    Placeholder values (``test-key``, empty, ``your-api-key``, …) are stripped
    from every source — they cannot block a real value in a later source.
    """
    if os.getenv("DICTON_DISABLE_ENV_FILE_LOAD", "").lower() == "true":
        return None

    explicit_env = os.getenv("DICTON_ENV_FILE")
    if explicit_env:
        env_path = Path(explicit_env).expanduser()
        if env_path.exists():
            load_dotenv(env_path)
            return str(env_path)
        return None

    loaded: list[str] = []

    # 1. User config dir — highest precedence for non-placeholder values
    dicton_env = get_user_env_path()
    if _merge_env_file(dicton_env, override=True):
        loaded.append(str(dicton_env))

    # 2. CWD (dev), distinct from the above
    cwd_env = Path.cwd() / ".env"
    if cwd_env.resolve() != dicton_env.resolve() and _merge_env_file(cwd_env, override=True):
        loaded.append(str(cwd_env))

    # 3. User-wide ~/.env — fills any hole left by placeholders above
    home_env = Path.home() / ".env"
    if (
        home_env.resolve() != dicton_env.resolve()
        and home_env.resolve() != cwd_env.resolve()
        and _merge_env_file(home_env, override=False)
    ):
        loaded.append(str(home_env))

    # 4. System install fallback
    sys_env = Path("/opt/dicton/.env")
    if _merge_env_file(sys_env, override=False):
        loaded.append(str(sys_env))

    if not loaded:
        # Last resort: let dotenv search normally
        load_dotenv()
        return None

    return ", ".join(loaded)


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
    CONFIG_DIR = get_user_config_dir()
    DATA_DIR = get_user_data_dir()
    MODELS_DIR = DATA_DIR / "models"

    # ElevenLabs API
    ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")

    # LLM Provider selection: "gemini" or "anthropic"
    # The primary provider will be used first, with fallback to the other if available
    LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini").lower()

    # Gemini API (for reformulation and translation). Model is pinned in code
    # (see adapters.llm.gemini.DEFAULT_GEMINI_MODEL); GEMINI_MODEL is ignored.
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

    # Anthropic API (alternative for reformulation and translation)
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
    ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")

    # ElevenLabs STT model
    ELEVENLABS_MODEL = os.getenv("ELEVENLABS_MODEL", "scribe_v1")

    # Mistral STT. Model is pinned in code
    # (see adapters.stt.mistral.MistralSTTProvider.DEFAULT_MODEL); MISTRAL_STT_MODEL is ignored.
    MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "")

    # Groq STT (Whisper Large v3 Turbo). Model is pinned in code
    # (see adapters.stt.groq.GroqSTTProvider.DEFAULT_MODEL); GROQ_STT_MODEL is ignored.
    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

    # STT Provider selection: "groq", "mistral", "elevenlabs", or "auto" (tries fallback order)
    STT_PROVIDER = os.getenv("STT_PROVIDER", "auto")

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
    # Double-tap window in ms - second press within this triggers toggle mode
    HOTKEY_DOUBLE_TAP_WINDOW_MS = int(os.getenv("HOTKEY_DOUBLE_TAP_WINDOW_MS", "300"))

    # Secondary hotkeys - alternative keys that work like FN (for keyboards without KEY_WAKEUP)
    # Options: escape, f1-f12, capslock, pause, insert, home, end, pageup, pagedown, none
    SECONDARY_HOTKEY = os.getenv("SECONDARY_HOTKEY", "none").lower()  # Basic/Reformulation mode
    SECONDARY_HOTKEY_TRANSLATION = os.getenv(
        "SECONDARY_HOTKEY_TRANSLATION", "none"
    ).lower()  # Translation mode

    # Keep the default UI focused on direct dictation + translation.
    ENABLE_ADVANCED_MODES = os.getenv("ENABLE_ADVANCED_MODES", "false").lower() == "true"

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
    # Normalisation divisor for RMS → 0-1 range (≈ int16 max / 4).
    # Shared by the visualizer and chunk-manager silence detector.
    RMS_NORMALIZATION = 8000

    # Chunked pipeline (long recordings)
    CHUNK_ENABLED = os.getenv("CHUNK_ENABLED", "true").lower() == "true"
    CHUNK_MIN_S = float(os.getenv("CHUNK_MIN_S", "30"))
    CHUNK_MAX_S = float(os.getenv("CHUNK_MAX_S", "120"))
    CHUNK_OVERLAP_S = float(os.getenv("CHUNK_OVERLAP_S", "2.0"))
    CHUNK_SILENCE_THRESHOLD = float(os.getenv("CHUNK_SILENCE_THRESHOLD", "0.03"))
    CHUNK_SILENCE_WINDOW_S = float(os.getenv("CHUNK_SILENCE_WINDOW_S", "0.3"))

    # Audio control during recording (Linux only)
    # Mute playback while recording (pauses players, then mutes sink if needed)
    MUTE_PLAYBACK_ON_RECORDING = os.getenv("MUTE_PLAYBACK_ON_RECORDING", "true").lower() == "true"
    # Backend for mute control: auto, playerctl, pipewire, pulseaudio
    MUTE_BACKEND = os.getenv("MUTE_BACKEND", "auto").lower()
    # Playback mute strategy: auto, pause, mute
    PLAYBACK_MUTE_STRATEGY = os.getenv("PLAYBACK_MUTE_STRATEGY", "auto").lower()

    # Set to device index number to force specific mic, or "auto"
    MIC_DEVICE = os.getenv("MIC_DEVICE", "auto")

    # Language: "auto" (None), "en", "fr", etc. (ISO-639-1 or ISO-639-3)
    LANGUAGE = os.getenv("LANGUAGE", "auto")

    # Filler word filtering: "true" to enable removal of filler words (um, uh, like, etc.)
    FILTER_FILLERS = os.getenv("FILTER_FILLERS", "true").lower() == "true"

    # LLM-based reformulation: "true" to enable light reformulation via configured LLM_PROVIDER
    # When enabled, uses LLM for smarter cleanup. When disabled, uses local filler removal only.
    ENABLE_REFORMULATION = os.getenv("ENABLE_REFORMULATION", "false").lower() == "true"

    # Paste threshold: texts with more words than this will use clipboard paste
    # instead of character-by-character streaming (faster for long dictations)
    # Set to 0 to always use streaming, or -1 to always use paste (default)
    PASTE_THRESHOLD_WORDS = int(os.getenv("PASTE_THRESHOLD_WORDS", "-1"))

    # Clipboard timing settings — DEPRECATED.
    # The verify-clipboard poll loop is disabled by default since Dicton 1.14.0
    # (xclip is synchronous on selection ownership on plain X11). These knobs
    # only take effect when the LinuxTextOutput ``verify_clipboard`` flag is
    # opted in. Kept for back-compat with existing .env files.
    CLIPBOARD_VERIFY_DELAY_MS = int(os.getenv("CLIPBOARD_VERIFY_DELAY_MS", "50"))
    CLIPBOARD_MAX_RETRIES = int(os.getenv("CLIPBOARD_MAX_RETRIES", "5"))

    DEBUG = os.getenv("DEBUG", "false").lower() == "true"

    # Desktop notifications - show notifications for recording start/stop/errors
    # Disabled by default since the visualizer provides sufficient feedback
    NOTIFICATIONS_ENABLED = os.getenv("NOTIFICATIONS_ENABLED", "false").lower() == "true"

    @classmethod
    def reload_config(cls):
        """Re-read all env-based class attributes from os.environ.

        Must be called after os.environ is updated at runtime (e.g. by
        save_config) so that the singleton ``config`` object reflects the
        new values.  Path-derived and constant attributes are left
        untouched.
        """
        cls.ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
        cls.LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini").lower()
        cls.GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
        cls.ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
        cls.ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
        cls.ELEVENLABS_MODEL = os.getenv("ELEVENLABS_MODEL", "scribe_v1")
        cls.MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "")
        cls.GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
        cls.STT_PROVIDER = os.getenv("STT_PROVIDER", "auto")
        cls.API_TIMEOUT = float(os.getenv("API_TIMEOUT", "30"))
        cls.STT_TIMEOUT = float(os.getenv("STT_TIMEOUT", "120"))
        cls.HOTKEY_MODIFIER = os.getenv("HOTKEY_MODIFIER", "alt")
        cls.HOTKEY_KEY = os.getenv("HOTKEY_KEY", "g")
        cls.HOTKEY_BASE = os.getenv("HOTKEY_BASE", "fn")
        cls.CUSTOM_HOTKEY_VALUE = os.getenv("CUSTOM_HOTKEY_VALUE", "alt+g")
        cls.HOTKEY_DOUBLE_TAP_WINDOW_MS = int(os.getenv("HOTKEY_DOUBLE_TAP_WINDOW_MS", "300"))
        cls.SECONDARY_HOTKEY = os.getenv("SECONDARY_HOTKEY", "none").lower()
        cls.SECONDARY_HOTKEY_TRANSLATION = os.getenv("SECONDARY_HOTKEY_TRANSLATION", "none").lower()
        cls.ENABLE_ADVANCED_MODES = os.getenv("ENABLE_ADVANCED_MODES", "false").lower() == "true"
        cls.THEME_COLOR = os.getenv("THEME_COLOR", "orange").lower()
        cls.ANIMATION_POSITION = os.getenv("ANIMATION_POSITION", "top-right").lower()
        cls.VISUALIZER_STYLE = os.getenv("VISUALIZER_STYLE", "toric").lower()
        cls.VISUALIZER_BACKEND = os.getenv("VISUALIZER_BACKEND", "pygame").lower()
        cls.VISUALIZER_OPACITY = float(os.getenv("VISUALIZER_OPACITY", "0.85"))
        cls.CHUNK_ENABLED = os.getenv("CHUNK_ENABLED", "true").lower() == "true"
        cls.CHUNK_MIN_S = float(os.getenv("CHUNK_MIN_S", "30"))
        cls.CHUNK_MAX_S = float(os.getenv("CHUNK_MAX_S", "120"))
        cls.CHUNK_OVERLAP_S = float(os.getenv("CHUNK_OVERLAP_S", "2.0"))
        cls.CHUNK_SILENCE_THRESHOLD = float(os.getenv("CHUNK_SILENCE_THRESHOLD", "0.03"))
        cls.CHUNK_SILENCE_WINDOW_S = float(os.getenv("CHUNK_SILENCE_WINDOW_S", "0.3"))
        cls.MUTE_PLAYBACK_ON_RECORDING = (
            os.getenv("MUTE_PLAYBACK_ON_RECORDING", "true").lower() == "true"
        )
        cls.MUTE_BACKEND = os.getenv("MUTE_BACKEND", "auto").lower()
        cls.PLAYBACK_MUTE_STRATEGY = os.getenv("PLAYBACK_MUTE_STRATEGY", "auto").lower()
        cls.MIC_DEVICE = os.getenv("MIC_DEVICE", "auto")
        cls.LANGUAGE = os.getenv("LANGUAGE", "auto")
        cls.FILTER_FILLERS = os.getenv("FILTER_FILLERS", "true").lower() == "true"
        cls.ENABLE_REFORMULATION = os.getenv("ENABLE_REFORMULATION", "false").lower() == "true"
        cls.PASTE_THRESHOLD_WORDS = int(os.getenv("PASTE_THRESHOLD_WORDS", "-1"))
        cls.CLIPBOARD_VERIFY_DELAY_MS = int(os.getenv("CLIPBOARD_VERIFY_DELAY_MS", "50"))
        cls.CLIPBOARD_MAX_RETRIES = int(os.getenv("CLIPBOARD_MAX_RETRIES", "5"))
        cls.DEBUG = os.getenv("DEBUG", "false").lower() == "true"
        cls.NOTIFICATIONS_ENABLED = os.getenv("NOTIFICATIONS_ENABLED", "false").lower() == "true"

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
