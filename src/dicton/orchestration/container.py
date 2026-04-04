"""Composition root for Dicton runtime services."""

from __future__ import annotations

from pathlib import Path

from ..adapters.audio.capture_adapter import AudioCaptureAdapter
from ..adapters.audio.chunk_manager import ChunkConfig, ChunkManager
from ..adapters.audio.recognizer import SpeechRecognizer
from ..adapters.audio.session_control import get_audio_session_control
from ..adapters.audio.stt_adapter import STTAdapter
from ..adapters.config.config_env import load_app_config
from ..adapters.config.latency import get_latency_tracker
from ..adapters.config.metrics import MetricsAdapter
from ..adapters.config.text_processing import TextOutputAdapter, TextProcessorAdapter
from ..adapters.input.hotkey_listener import HotkeyListener
from ..adapters.llm.factory import get_llm_provider_with_fallback
from ..adapters.output.factory import get_text_output
from ..adapters.output.selection_factory import get_selection_reader
from ..adapters.ui.notifications_factory import get_notification_service
from ..adapters.ui.theme_constants import FLEXOKI_COLORS, get_animation_position, get_theme_colors
from ..adapters.ui.visualizer_config import VisualizerConfig
from ..core.config_model import AppConfig
from ..core.controller import DictationController
from ..shared.app_paths import get_user_config_dir, get_user_data_dir
from .runtime_service import RuntimeService
from .session_service import SessionService


def _build_visualizer_config(app_config: AppConfig) -> VisualizerConfig:
    """Resolve all visualizer settings into a single config dataclass."""
    theme_color = app_config.theme_color
    anim_pos = app_config.animation_position

    return VisualizerConfig(
        theme_colors=get_theme_colors(theme_color),
        flexoki_colors=FLEXOKI_COLORS,
        rms_normalization=app_config.rms_normalization,
        animation_position_fn=lambda w, h, s: get_animation_position(anim_pos, w, h, s),
        debug=app_config.debug,
        opacity=app_config.visualizer_opacity,
        visualizer_style=app_config.visualizer_style,
    )


def _build_visualizer_factory(app_config: AppConfig):
    """Create a callable that returns a fresh visualizer instance or None."""
    backend = app_config.visualizer_backend
    viz_config = _build_visualizer_config(app_config)

    def _factory():
        try:
            if backend == "gtk":
                try:
                    from ..adapters.ui.visualizer_gtk import get_visualizer
                except ImportError:
                    from ..adapters.ui.visualizer import get_visualizer
            elif backend == "vispy":
                try:
                    from ..adapters.ui.visualizer_vispy import get_visualizer
                except ImportError:
                    from ..adapters.ui.visualizer import get_visualizer
            else:
                from ..adapters.ui.visualizer import get_visualizer
            return get_visualizer(viz_config)
        except Exception:
            return None

    return _factory


def build_runtime_service(log_path: Path | None = None) -> RuntimeService:
    """Build the runtime service with the current production adapters."""
    # Ensure user directories exist
    config_dir = get_user_config_dir()
    data_dir = get_user_data_dir()
    models_dir = data_dir / "models"
    config_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)
    models_dir.mkdir(parents=True, exist_ok=True)

    app_config = load_app_config()

    # === Audio providers ===
    recognizer = SpeechRecognizer(
        sample_rate=app_config.sample_rate,
        chunk_size=app_config.chunk_size,
        mic_device=app_config.mic_device,
        debug=app_config.debug,
        visualizer_factory=_build_visualizer_factory(app_config),
    )
    chunk_manager = None
    if app_config.chunk_enabled:
        chunk_config = ChunkConfig(
            enabled=app_config.chunk_enabled,
            min_chunk_s=app_config.chunk_min_s,
            max_chunk_s=app_config.chunk_max_s,
            overlap_s=app_config.chunk_overlap_s,
            silence_threshold=app_config.chunk_silence_threshold,
            silence_window_s=app_config.chunk_silence_window_s,
            chunk_size=app_config.chunk_size,
            sample_rate=app_config.sample_rate,
            stt_timeout=app_config.stt_timeout,
            rms_normalization=float(app_config.rms_normalization),
        )
        chunk_manager = ChunkManager(
            stt_provider=recognizer.stt_provider,
            config=chunk_config,
        )

    # === Platform adapters ===
    selection_reader = get_selection_reader(debug=app_config.debug)
    text_output = get_text_output(
        selection_reader,
        paste_threshold_words=app_config.paste_threshold_words,
        debug=app_config.debug,
        clipboard_verify_delay_ms=app_config.clipboard_verify_delay_ms,
        clipboard_max_retries=app_config.clipboard_max_retries,
    )
    audio_control = get_audio_session_control(
        mute_playback=app_config.mute_playback_on_recording,
        mute_strategy=app_config.playback_mute_strategy,
        mute_backend=app_config.mute_backend,
    )
    notification_service = get_notification_service(
        notifications_enabled=app_config.notifications_enabled,
    )

    # === LLM + visualizer ===
    llm_provider = get_llm_provider_with_fallback(user_provider=app_config.llm_provider)

    # === Config / metrics ===
    metrics = get_latency_tracker()

    # === Input ===
    hotkey_listener = HotkeyListener(
        None,
        hotkey_modifier=app_config.hotkey_modifier,
        hotkey_key=app_config.hotkey_key,
    )

    # === Wiring ===
    session_service = SessionService(
        controller=None,
        text_output=text_output,
        metrics=metrics,
        app_config=app_config,
        selection_reader=selection_reader,
        notification_service=notification_service,
        llm_provider=llm_provider,
        visualizer_factory=_build_visualizer_factory(app_config),
    )
    session_service.bind_controller(
        DictationController(
            audio_capture=AudioCaptureAdapter(recognizer, chunk_manager=chunk_manager),
            audio_control=audio_control,
            stt=STTAdapter(recognizer, chunk_manager=chunk_manager),
            text_processor=TextProcessorAdapter(session_service.process_text),
            text_output=TextOutputAdapter(session_service.output_result),
            ui=notification_service,
            metrics=MetricsAdapter(metrics),
        )
    )
    hotkey_listener.on_toggle = session_service.toggle_basic_recording

    return RuntimeService(
        session_service=session_service,
        keyboard=hotkey_listener,
        recognizer=recognizer,
        app_config=app_config,
        log_path=log_path,
        chunk_manager=chunk_manager,
        notification_service=notification_service,
    )
