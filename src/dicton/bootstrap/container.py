"""Composition root for Dicton runtime services."""

from __future__ import annotations

from ..adapters.audio import AudioCaptureAdapter, STTAdapter
from ..adapters.audio_session_control import AudioSessionControlAdapter
from ..adapters.config_env import load_app_config
from ..adapters.metrics import MetricsAdapter
from ..adapters.text_processing import TextOutputAdapter, TextProcessorAdapter
from ..adapters.ui_feedback import UIFeedbackAdapter
from ..application.runtime_service import RuntimeService
from ..application.session_service import SessionService
from ..config import config
from ..core.controller import DictationController
from ..keyboard_handler import KeyboardHandler
from ..latency_tracker import get_latency_tracker
from ..speech_recognition_engine import SpeechRecognizer


def build_runtime_service() -> RuntimeService:
    """Build the runtime service with the current production adapters."""
    config.create_dirs()
    recognizer = SpeechRecognizer()
    keyboard = KeyboardHandler(None)
    app_config = load_app_config()
    metrics = get_latency_tracker()

    session_service = SessionService(
        controller=None,
        keyboard=keyboard,
        metrics=metrics,
        app_config=app_config,
    )
    session_service.bind_controller(
        DictationController(
        audio_capture=AudioCaptureAdapter(recognizer),
        audio_control=AudioSessionControlAdapter(),
        stt=STTAdapter(recognizer),
        text_processor=TextProcessorAdapter(session_service.process_text),
        text_output=TextOutputAdapter(session_service.output_result),
        ui=UIFeedbackAdapter(),
        metrics=MetricsAdapter(metrics),
    )
    )
    keyboard.on_toggle = session_service.toggle_basic_recording

    return RuntimeService(
        session_service=session_service,
        keyboard=keyboard,
        recognizer=recognizer,
        app_config=app_config,
    )
