"""Regression tests for session-service orchestration and concurrency."""

from __future__ import annotations

import threading
import time
from contextlib import nullcontext

from dicton.core.processing_mode import ProcessingMode
from dicton.core.state_machine import SessionState
from dicton.orchestration.session_service import SessionService


class _SessionSummary:
    def total_duration_ms(self) -> float:
        return 1.0


class _Metrics:
    def __init__(self):
        self.started = False
        self.ended = False
        self.measures: list[str] = []

    def start_session(self) -> None:
        self.started = True

    def measure(self, name: str, **kwargs):
        self.measures.append(name)
        return nullcontext()

    def end_session(self):
        self.ended = True
        return _SessionSummary()


class _AppConfig:
    def __init__(self, *, enable_advanced_modes: bool = False, debug: bool = False):
        self.debug = debug
        self.enable_advanced_modes = enable_advanced_modes
        self.enable_reformulation = False
        self.llm_provider = "gemini"


class _Recognizer:
    def __init__(self, *, audio=b"audio", text="hello", on_record=None, delay: float = 0):
        self.audio = audio
        self.text = text
        self.on_record = on_record
        self.delay = delay
        self.record_calls = 0
        self.stop_calls = 0
        self.cancel_calls = 0
        self.transcribe_calls = 0

    def record(self, on_chunk=None):
        self.record_calls += 1
        if self.delay:
            time.sleep(self.delay)
        if self.on_record:
            self.on_record()
        return self.audio

    def stop(self) -> None:
        self.stop_calls += 1

    def cancel(self) -> None:
        self.cancel_calls += 1

    def transcribe(self, audio):
        self.transcribe_calls += 1
        return self.text

    def filter_text(self, text):
        return text


class _TextOutput:
    def __init__(self):
        self.insertions: list[tuple[str, int]] = []

    def insert_text(self, text: str, delay_ms: int = 50) -> None:
        self.insertions.append((text, delay_ms))

    def paste_text(self, text: str) -> bool:
        return False


class _Notifications:
    def __init__(self):
        self.calls: list[tuple[str, str]] = []

    def notify(self, title: str, message: str, timeout: int = 2) -> None:
        self.calls.append((title, message))


def _build_service(
    *,
    recognizer: _Recognizer | None = None,
    metrics: _Metrics | None = None,
    text_output: _TextOutput | None = None,
    app_config: _AppConfig | None = None,
    notifications: _Notifications | None = None,
):
    return SessionService(
        recognizer=recognizer or _Recognizer(),
        text_output=text_output or _TextOutput(),
        metrics=metrics or _Metrics(),
        app_config=app_config or _AppConfig(),
        notification_service=notifications,
        visualizer_factory=lambda: None,
    )


def test_session_service_happy_path_records_transcribes_processes_and_outputs():
    metrics = _Metrics()
    output = _TextOutput()
    service = _build_service(metrics=metrics, text_output=output)

    service._record_and_transcribe(ProcessingMode.BASIC)

    assert metrics.started is True
    assert metrics.ended is True
    assert metrics.measures == [
        "audio_capture",
        "stt_transcription",
        "text_processing",
        "text_output",
    ]
    assert output.insertions == [("hello", 50)]
    assert service._state.state is SessionState.IDLE


def test_session_service_no_audio_ends_session_without_output():
    metrics = _Metrics()
    output = _TextOutput()
    service = _build_service(recognizer=_Recognizer(audio=b""), metrics=metrics, text_output=output)

    service._record_and_transcribe(ProcessingMode.BASIC)

    assert metrics.ended is True
    assert output.insertions == []
    assert service._state.state is SessionState.IDLE


def test_session_service_cancel_during_recording_aborts_pipeline():
    service_ref: list[SessionService | None] = [None]

    def _cancel():
        service_ref[0].cancel_recording()

    metrics = _Metrics()
    output = _TextOutput()
    service = _build_service(
        recognizer=_Recognizer(audio=b"audio", on_record=_cancel),
        metrics=metrics,
        text_output=output,
    )
    service_ref[0] = service

    with service._session_lock:
        service._recording = True
    service._record_and_transcribe(ProcessingMode.BASIC)

    assert metrics.ended is True
    assert output.insertions == []
    assert service._state.state is SessionState.IDLE


def test_session_service_processing_failure_ends_without_output():
    metrics = _Metrics()
    output = _TextOutput()
    service = _build_service(metrics=metrics, text_output=output)
    service.process_text = lambda text, mode, selected_text=None: None

    service._record_and_transcribe(ProcessingMode.BASIC)

    assert metrics.ended is True
    assert output.insertions == []
    assert service._state.state is SessionState.IDLE


def test_exception_resets_state_and_ends_metrics_session():
    class _BoomRecognizer(_Recognizer):
        def transcribe(self, audio):
            raise RuntimeError("boom")

    metrics = _Metrics()
    notifications = _Notifications()
    service = _build_service(
        recognizer=_BoomRecognizer(),
        metrics=metrics,
        notifications=notifications,
    )

    service._record_and_transcribe(ProcessingMode.BASIC)

    assert service._state.state is SessionState.IDLE
    assert metrics.ended is True
    assert notifications.calls[-1] == ("❌ Error", "boom")


def test_cancel_after_transcription_aborts_before_text_processing():
    service_ref: list[SessionService | None] = [None]

    class _CancelAfterSTT(_Recognizer):
        def transcribe(self, audio):
            service_ref[0]._cancel_token.cancel()
            return "hello"

    output = _TextOutput()
    service = _build_service(recognizer=_CancelAfterSTT(), text_output=output)
    service_ref[0] = service
    service.process_text = lambda text, mode, selected_text=None: "should-not-run"

    service._record_and_transcribe(ProcessingMode.BASIC)

    assert output.insertions == []
    assert service._state.state is SessionState.IDLE


def test_public_cancel_during_processing_aborts_before_output():
    entered_transcribe = threading.Event()
    release_transcribe = threading.Event()

    class _BlockingSTT(_Recognizer):
        def transcribe(self, audio):
            entered_transcribe.set()
            release_transcribe.wait(timeout=1.0)
            return "hello"

    recognizer = _BlockingSTT()
    output = _TextOutput()
    service = _build_service(recognizer=recognizer, text_output=output)

    service.start_recording(ProcessingMode.BASIC)
    assert entered_transcribe.wait(timeout=1.0)
    service.cancel_recording()
    release_transcribe.set()
    assert service._record_thread is not None
    service._record_thread.join(timeout=1.0)

    assert recognizer.cancel_calls == 1
    assert output.insertions == []
    assert service._state.state is SessionState.IDLE


def test_add_state_observer_receives_session_state_transitions():
    service = _build_service()
    states: list[SessionState] = []
    service.add_state_observer(states.append)

    service._record_and_transcribe(ProcessingMode.BASIC)

    assert states == [
        SessionState.RECORDING,
        SessionState.PROCESSING,
        SessionState.OUTPUTTING,
        SessionState.IDLE,
    ]


def test_concurrent_starts_only_launch_one_session():
    recognizer = _Recognizer(delay=0.05)
    service = _build_service(recognizer=recognizer)

    threads = [
        threading.Thread(target=service.start_recording, args=(ProcessingMode.BASIC,)),
        threading.Thread(target=service.start_recording, args=(ProcessingMode.BASIC,)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    record_thread = service._record_thread
    assert record_thread is not None
    record_thread.join(timeout=1.0)

    assert recognizer.record_calls == 1
    assert service.recording is False


def test_start_recording_rejects_advanced_mode_when_disabled():
    service = _build_service(
        recognizer=_Recognizer(delay=0.05),
        app_config=_AppConfig(enable_advanced_modes=False),
    )

    service.start_recording(ProcessingMode.REFORMULATION)
    assert service._record_thread is not None
    service._record_thread.join(timeout=1.0)

    assert service._current_mode is ProcessingMode.BASIC


def test_start_recording_accepts_advanced_mode_when_enabled():
    service = _build_service(
        recognizer=_Recognizer(delay=0.05),
        app_config=_AppConfig(enable_advanced_modes=True),
    )

    service.start_recording(ProcessingMode.REFORMULATION)
    assert service._record_thread is not None
    service._record_thread.join(timeout=1.0)

    assert service._current_mode is ProcessingMode.REFORMULATION
