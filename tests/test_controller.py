from dicton.core.controller import DictationController, SessionContext
from dicton.core.ports import (
    AudioCapture,
    MetricsSink,
    STTService,
    TextOutput,
    TextProcessor,
    UIFeedback,
)


class _AudioCapture(AudioCapture):
    def __init__(self, audio=b"audio", on_record=None):
        self.audio = audio
        self.on_record = on_record
        self.stopped = False
        self.cancelled = False

    def record(self):
        if self.on_record:
            self.on_record()
        return self.audio

    def stop(self) -> None:
        self.stopped = True

    def cancel(self) -> None:
        self.cancelled = True


class _STT(STTService):
    def __init__(self, text="hello"):
        self.text = text

    def transcribe(self, audio):
        return self.text


class _TextProcessor(TextProcessor):
    def __init__(self, result="ok"):
        self.result = result

    def process(self, text: str, mode, selected_text=None):
        return self.result


class _TextOutput(TextOutput):
    def __init__(self):
        self.calls = []

    def output(self, text: str, mode, replace_selection: bool) -> None:
        self.calls.append((text, replace_selection))


class _UI(UIFeedback):
    def __init__(self):
        self.calls = []

    def notify(self, title: str, message: str) -> None:
        self.calls.append((title, message))


class _Metrics(MetricsSink):
    def __init__(self):
        self.started = False
        self.ended = False

    def start_session(self) -> None:
        self.started = True

    def measure(self, name: str, **kwargs):
        class _Ctx:
            def __enter__(self_inner):
                return None

            def __exit__(self_inner, exc_type, exc, tb):
                return False

        return _Ctx()

    def end_session(self):
        self.ended = True
        return {"ok": True}


def test_controller_happy_path():
    controller = DictationController(
        audio_capture=_AudioCapture(audio=b"audio"),
        stt=_STT(text="hello"),
        text_processor=_TextProcessor(result="done"),
        text_output=_TextOutput(),
        ui=_UI(),
        metrics=_Metrics(),
    )
    success, session = controller.run_session(
        mode="basic",
        session=SessionContext(selected_text=None),
        mode_names={"basic": "Recording"},
    )
    assert success is True
    assert session == {"ok": True}


def test_controller_no_audio():
    controller = DictationController(
        audio_capture=_AudioCapture(audio=b""),
        stt=_STT(text="hello"),
        text_processor=_TextProcessor(result="done"),
        text_output=_TextOutput(),
        ui=_UI(),
        metrics=_Metrics(),
    )
    success, session = controller.run_session(
        mode="basic",
        session=SessionContext(selected_text=None),
        mode_names={"basic": "Recording"},
    )
    assert success is False
    assert session == {"ok": True}


def test_controller_cancel_during_recording():
    controller = None

    def _cancel():
        controller.cancel()

    controller = DictationController(
        audio_capture=_AudioCapture(audio=b"audio", on_record=_cancel),
        stt=_STT(text="hello"),
        text_processor=_TextProcessor(result="done"),
        text_output=_TextOutput(),
        ui=_UI(),
        metrics=_Metrics(),
    )
    success, session = controller.run_session(
        mode="basic",
        session=SessionContext(selected_text=None),
        mode_names={"basic": "Recording"},
    )
    assert success is False
    assert session == {"ok": True}


def test_controller_processing_failure():
    controller = DictationController(
        audio_capture=_AudioCapture(audio=b"audio"),
        stt=_STT(text="hello"),
        text_processor=_TextProcessor(result=None),
        text_output=_TextOutput(),
        ui=_UI(),
        metrics=_Metrics(),
    )
    success, session = controller.run_session(
        mode="basic",
        session=SessionContext(selected_text=None),
        mode_names={"basic": "Recording"},
    )
    assert success is False
    assert session == {"ok": True}


def test_exception_resets_state():
    """Exception during pipeline resets state machine to IDLE and re-raises."""
    from dicton.core.state_machine import SessionState

    class _BoomSTT(STTService):
        def transcribe(self, audio):
            raise RuntimeError("boom")

    metrics = _Metrics()
    controller = DictationController(
        audio_capture=_AudioCapture(audio=b"audio"),
        stt=_BoomSTT(),
        text_processor=_TextProcessor(result="ok"),
        text_output=_TextOutput(),
        ui=_UI(),
        metrics=metrics,
    )

    import pytest

    with pytest.raises(RuntimeError, match="boom"):
        controller.run_session(
            mode="basic",
            session=SessionContext(selected_text=None),
            mode_names={"basic": "Recording"},
        )

    assert controller._state.state == SessionState.IDLE
    assert metrics.ended is True


def test_cancel_after_transcription():
    """Cancel token set after STT returns should abort before text processing."""

    class _CancelAfterSTT(STTService):
        def __init__(self, controller_ref):
            self._controller_ref = controller_ref

        def transcribe(self, audio):
            self._controller_ref[0]._cancel_token.cancel()
            return "hello"

    controller_ref = [None]
    controller = DictationController(
        audio_capture=_AudioCapture(audio=b"audio"),
        stt=_CancelAfterSTT(controller_ref),
        text_processor=_TextProcessor(result="ok"),
        text_output=_TextOutput(),
        ui=_UI(),
        metrics=_Metrics(),
    )
    controller_ref[0] = controller

    success, session = controller.run_session(
        mode="basic",
        session=SessionContext(selected_text=None),
        mode_names={"basic": "Recording"},
    )
    assert success is False
