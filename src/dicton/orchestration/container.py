"""Composition root for Dicton runtime services."""

from __future__ import annotations

from pathlib import Path

from ..adapters.audio.capture_adapter import AudioCaptureAdapter
from ..adapters.audio.chunk_manager import ChunkConfig, ChunkManager
from ..adapters.audio.recognizer import SpeechRecognizer
from ..adapters.audio.session_control import get_audio_session_control
from ..adapters.audio.stt_adapter import STTAdapter
from ..adapters.config.config_env import load_app_config
from ..adapters.config.metrics import MetricsAdapter
from ..adapters.config.text_processing import TextOutputAdapter, TextProcessorAdapter
from ..adapters.input.hotkey_listener import HotkeyListener
from ..adapters.llm.factory import get_llm_provider_with_fallback
from ..adapters.output.factory import get_text_output
from ..adapters.output.selection_factory import get_selection_reader
from ..adapters.ui.notifications_factory import get_notification_service
from ..core.controller import DictationController
from ..shared.config import config
from ..shared.latency_tracker import get_latency_tracker
from .runtime_service import RuntimeService
from .session_service import SessionService


def _build_visualizer_factory():
    """Create a callable that returns a fresh visualizer instance or None."""
    backend = config.VISUALIZER_BACKEND

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
            return get_visualizer()
        except Exception:
            return None

    return _factory


def build_runtime_service(log_path: Path | None = None) -> RuntimeService:
    """Build the runtime service with the current production adapters."""
    config.create_dirs()

    # === Audio providers ===
    recognizer = SpeechRecognizer()
    chunk_manager = None
    if config.CHUNK_ENABLED:
        chunk_config = ChunkConfig.from_app_config(config)
        chunk_manager = ChunkManager(
            stt_provider=recognizer.stt_provider,
            config=chunk_config,
        )

    # === Platform adapters ===
    selection_reader = get_selection_reader()
    text_output = get_text_output(selection_reader)
    audio_control = get_audio_session_control()
    notification_service = get_notification_service()

    # === LLM + visualizer ===
    llm_provider = get_llm_provider_with_fallback()
    visualizer_factory = _build_visualizer_factory()

    # === Config / metrics ===
    app_config = load_app_config()
    metrics = get_latency_tracker()

    # === Input ===
    hotkey_listener = HotkeyListener(None)

    # === Wiring ===
    session_service = SessionService(
        controller=None,
        text_output=text_output,
        metrics=metrics,
        app_config=app_config,
        selection_reader=selection_reader,
        notification_service=notification_service,
        llm_provider=llm_provider,
        visualizer_factory=visualizer_factory,
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
