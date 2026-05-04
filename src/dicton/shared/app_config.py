"""Structured runtime configuration snapshot."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AppConfig:
    # -- General ----------------------------------------------------------
    debug: bool
    notifications_enabled: bool
    language: str

    # -- STT --------------------------------------------------------------
    stt_provider: str
    elevenlabs_api_key: str
    elevenlabs_model: str
    mistral_api_key: str
    api_timeout: float
    stt_timeout: float

    # -- LLM --------------------------------------------------------------
    llm_provider: str
    gemini_api_key: str
    anthropic_api_key: str
    anthropic_model: str

    # -- Hotkey -----------------------------------------------------------
    hotkey_modifier: str
    hotkey_key: str
    hotkey_base: str
    custom_hotkey_value: str
    hotkey_double_tap_window_ms: int
    secondary_hotkey: str
    secondary_hotkey_translation: str

    # -- Audio ------------------------------------------------------------
    sample_rate: int
    chunk_size: int
    rms_normalization: int
    mic_device: str
    mute_playback_on_recording: bool
    mute_backend: str
    playback_mute_strategy: str

    # -- Chunking ---------------------------------------------------------
    chunk_enabled: bool
    chunk_min_s: float
    chunk_max_s: float
    chunk_overlap_s: float
    chunk_silence_threshold: float
    chunk_silence_window_s: float

    # -- Visualizer -------------------------------------------------------
    theme_color: str
    animation_position: str
    visualizer_style: str
    visualizer_backend: str
    visualizer_opacity: float

    # -- Text processing --------------------------------------------------
    filter_fillers: bool
    enable_reformulation: bool
    enable_advanced_modes: bool
    paste_threshold_words: int
    clipboard_verify_delay_ms: int
    clipboard_max_retries: int

    # -- Transcript cleaning ---------------------------------------------
    enable_transcript_cleaning: bool
    transcript_cleaner_provider: str
    transcript_cleaner_model: str
    transcript_cleaner_timeout_s: float
