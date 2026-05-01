"""Env configuration adapter producing a structured AppConfig.

Reads all configuration values directly from ``os.environ``.  The dotenv
loading is guaranteed by importing ``shared.app_paths`` (which triggers
the ``shared.config`` module-level ``_load_env_files()`` via Python's
import chain).  This adapter does **not** import the legacy
``shared.config`` singleton—callers get a frozen ``AppConfig`` snapshot
that can be threaded through the application without global mutable state.
"""

from __future__ import annotations

import os

from ...shared.app_config import AppConfig


def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default)


def _env_lower(key: str, default: str = "") -> str:
    return os.getenv(key, default).lower()


def _env_bool(key: str, default: str = "false") -> bool:
    return os.getenv(key, default).lower() == "true"


def _env_float(key: str, default: str) -> float:
    return float(os.getenv(key, default))


def _env_int(key: str, default: str) -> int:
    return int(os.getenv(key, default))


def load_app_config() -> AppConfig:
    """Build an ``AppConfig`` from the current ``os.environ`` state."""
    return AppConfig(
        # General
        debug=_env_bool("DEBUG", "false"),
        notifications_enabled=_env_bool("NOTIFICATIONS_ENABLED", "false"),
        language=_env("LANGUAGE", "auto"),
        # STT
        stt_provider=_env("STT_PROVIDER", "auto"),
        elevenlabs_api_key=_env("ELEVENLABS_API_KEY"),
        elevenlabs_model=_env("ELEVENLABS_MODEL", "scribe_v1"),
        mistral_api_key=_env("MISTRAL_API_KEY"),
        mistral_stt_model=_env("MISTRAL_STT_MODEL", "voxtral-mini-latest"),
        api_timeout=_env_float("API_TIMEOUT", "30"),
        stt_timeout=_env_float("STT_TIMEOUT", "120"),
        # LLM
        llm_provider=_env_lower("LLM_PROVIDER", "gemini"),
        gemini_api_key=_env("GEMINI_API_KEY"),
        gemini_model=_env("GEMINI_MODEL", "gemini-2.5-flash-lite"),
        anthropic_api_key=_env("ANTHROPIC_API_KEY"),
        anthropic_model=_env("ANTHROPIC_MODEL", "claude-sonnet-4-20250514"),
        # Hotkey
        hotkey_modifier=_env("HOTKEY_MODIFIER", "alt"),
        hotkey_key=_env("HOTKEY_KEY", "g"),
        hotkey_base=_env("HOTKEY_BASE", "fn"),
        custom_hotkey_value=_env("CUSTOM_HOTKEY_VALUE", "alt+g"),
        hotkey_double_tap_window_ms=_env_int("HOTKEY_DOUBLE_TAP_WINDOW_MS", "300"),
        secondary_hotkey=_env_lower("SECONDARY_HOTKEY", "none"),
        secondary_hotkey_translation=_env_lower("SECONDARY_HOTKEY_TRANSLATION", "none"),
        # Audio
        sample_rate=16000,
        chunk_size=1024,
        rms_normalization=8000,
        mic_device=_env("MIC_DEVICE", "auto"),
        mute_playback_on_recording=_env_bool("MUTE_PLAYBACK_ON_RECORDING", "true"),
        mute_backend=_env_lower("MUTE_BACKEND", "auto"),
        playback_mute_strategy=_env_lower("PLAYBACK_MUTE_STRATEGY", "auto"),
        # Chunking
        chunk_enabled=_env_bool("CHUNK_ENABLED", "true"),
        chunk_min_s=_env_float("CHUNK_MIN_S", "30"),
        chunk_max_s=_env_float("CHUNK_MAX_S", "120"),
        chunk_overlap_s=_env_float("CHUNK_OVERLAP_S", "2.0"),
        chunk_silence_threshold=_env_float("CHUNK_SILENCE_THRESHOLD", "0.03"),
        chunk_silence_window_s=_env_float("CHUNK_SILENCE_WINDOW_S", "0.3"),
        # Visualizer
        theme_color=_env_lower("THEME_COLOR", "orange"),
        animation_position=_env_lower("ANIMATION_POSITION", "top-right"),
        visualizer_style=_env_lower("VISUALIZER_STYLE", "toric"),
        visualizer_backend=_env_lower("VISUALIZER_BACKEND", "pygame"),
        visualizer_opacity=_env_float("VISUALIZER_OPACITY", "0.85"),
        # Text processing
        filter_fillers=_env_bool("FILTER_FILLERS", "true"),
        enable_reformulation=_env_bool("ENABLE_REFORMULATION", "false"),
        enable_advanced_modes=_env_bool("ENABLE_ADVANCED_MODES", "false"),
        paste_threshold_words=_env_int("PASTE_THRESHOLD_WORDS", "10"),
        clipboard_verify_delay_ms=_env_int("CLIPBOARD_VERIFY_DELAY_MS", "50"),
        clipboard_max_retries=_env_int("CLIPBOARD_MAX_RETRIES", "5"),
    )
