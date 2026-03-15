"""Composition root for Dicton runtime services."""

from __future__ import annotations

from pathlib import Path

from ..adapters.audio import AudioCaptureAdapter, STTAdapter
from ..adapters.audio_session_control import AudioSessionControlAdapter
from ..adapters.config_env import load_app_config
from ..adapters.metrics import MetricsAdapter
from ..adapters.text_processing import TextOutputAdapter, TextProcessorAdapter
from ..application.runtime_service import RuntimeService
from ..application.session_service import SessionService
from ..chunk_manager import ChunkConfig, ChunkManager
from ..config import config
from ..core.controller import DictationController
from ..input.hotkey_listener import HotkeyListener
from ..latency_tracker import get_latency_tracker
from ..output.factory import get_text_output
from ..output.selection_factory import get_selection_reader
from ..speech_recognition_engine import SpeechRecognizer
from ..ui.notifications_factory import get_notification_service


def build_runtime_service(log_path: Path | None = None) -> RuntimeService:
    """Build the runtime service with the current production adapters."""
    config.create_dirs()
    recognizer = SpeechRecognizer()
    chunk_manager = None
    if config.CHUNK_ENABLED:
        chunk_config = ChunkConfig.from_app_config(config)
        chunk_manager = ChunkManager(
            stt_provider=recognizer.stt_provider,
            config=chunk_config,
        )
    hotkey_listener = HotkeyListener(None)
    selection_reader = get_selection_reader()
    text_output = get_text_output(selection_reader)
    notification_service = get_notification_service()
    app_config = load_app_config()
    metrics = get_latency_tracker()

    session_service = SessionService(
        controller=None,
        text_output=text_output,
        metrics=metrics,
        app_config=app_config,
        selection_reader=selection_reader,
        notification_service=notification_service,
    )
    session_service.bind_controller(
        DictationController(
            audio_capture=AudioCaptureAdapter(recognizer, chunk_manager=chunk_manager),
            audio_control=AudioSessionControlAdapter(),
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
