"""Env configuration adapter producing a structured AppConfig.

Reads values from the legacy ``shared.config.Config`` singleton (which itself
reads ``os.environ`` / ``.env`` files) and returns a frozen ``AppConfig``
snapshot.  The legacy module is **not** removed yet — this adapter simply
routes its values through the structured model so that the rest of the
application can migrate incrementally.
"""

from __future__ import annotations

from ...core.config_model import AppConfig
from ...shared.config import config as legacy_config


def load_app_config() -> AppConfig:
    """Build an ``AppConfig`` from the current legacy config state."""
    return AppConfig(
        # General
        debug=legacy_config.DEBUG,
        notifications_enabled=legacy_config.NOTIFICATIONS_ENABLED,
        language=legacy_config.LANGUAGE,
        # STT
        stt_provider=legacy_config.STT_PROVIDER,
        elevenlabs_api_key=legacy_config.ELEVENLABS_API_KEY,
        elevenlabs_model=legacy_config.ELEVENLABS_MODEL,
        mistral_api_key=legacy_config.MISTRAL_API_KEY,
        mistral_stt_model=legacy_config.MISTRAL_STT_MODEL,
        api_timeout=legacy_config.API_TIMEOUT,
        stt_timeout=legacy_config.STT_TIMEOUT,
        # LLM
        llm_provider=legacy_config.LLM_PROVIDER,
        gemini_api_key=legacy_config.GEMINI_API_KEY,
        gemini_model=legacy_config.GEMINI_MODEL,
        anthropic_api_key=legacy_config.ANTHROPIC_API_KEY,
        anthropic_model=legacy_config.ANTHROPIC_MODEL,
        # Hotkey
        hotkey_modifier=legacy_config.HOTKEY_MODIFIER,
        hotkey_key=legacy_config.HOTKEY_KEY,
        hotkey_base=legacy_config.HOTKEY_BASE,
        custom_hotkey_value=legacy_config.CUSTOM_HOTKEY_VALUE,
        hotkey_double_tap_window_ms=legacy_config.HOTKEY_DOUBLE_TAP_WINDOW_MS,
        secondary_hotkey=legacy_config.SECONDARY_HOTKEY,
        secondary_hotkey_translation=legacy_config.SECONDARY_HOTKEY_TRANSLATION,
        secondary_hotkey_act_on_text=legacy_config.SECONDARY_HOTKEY_ACT_ON_TEXT,
        # Audio
        sample_rate=legacy_config.SAMPLE_RATE,
        chunk_size=legacy_config.CHUNK_SIZE,
        rms_normalization=legacy_config.RMS_NORMALIZATION,
        mic_device=legacy_config.MIC_DEVICE,
        mute_playback_on_recording=legacy_config.MUTE_PLAYBACK_ON_RECORDING,
        mute_backend=legacy_config.MUTE_BACKEND,
        playback_mute_strategy=legacy_config.PLAYBACK_MUTE_STRATEGY,
        # Chunking
        chunk_enabled=legacy_config.CHUNK_ENABLED,
        chunk_min_s=legacy_config.CHUNK_MIN_S,
        chunk_max_s=legacy_config.CHUNK_MAX_S,
        chunk_overlap_s=legacy_config.CHUNK_OVERLAP_S,
        chunk_silence_threshold=legacy_config.CHUNK_SILENCE_THRESHOLD,
        chunk_silence_window_s=legacy_config.CHUNK_SILENCE_WINDOW_S,
        # Visualizer
        theme_color=legacy_config.THEME_COLOR,
        animation_position=legacy_config.ANIMATION_POSITION,
        visualizer_style=legacy_config.VISUALIZER_STYLE,
        visualizer_backend=legacy_config.VISUALIZER_BACKEND,
        visualizer_opacity=legacy_config.VISUALIZER_OPACITY,
        # Text processing
        filter_fillers=legacy_config.FILTER_FILLERS,
        enable_reformulation=legacy_config.ENABLE_REFORMULATION,
        enable_advanced_modes=legacy_config.ENABLE_ADVANCED_MODES,
        paste_threshold_words=legacy_config.PASTE_THRESHOLD_WORDS,
        clipboard_verify_delay_ms=legacy_config.CLIPBOARD_VERIFY_DELAY_MS,
        clipboard_max_retries=legacy_config.CLIPBOARD_MAX_RETRIES,
    )
