"""Core orchestration for Dicton.

Keeps the record -> transcribe -> process -> output pipeline in one place,
decoupled from platform/vendor-specific implementations via ports.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .cancel_token import CancelToken
from .ports import AudioCapture, MetricsSink, STTService, TextOutput, TextProcessor, UIFeedback
from .state_machine import SessionEvent, SessionStateMachine


if TYPE_CHECKING:
    from ..context_detector import ContextInfo


@dataclass(frozen=True)
class SessionContext:
    """Container for optional session details passed to the controller."""

    selected_text: str | None = None
    context: ContextInfo | None = None


class DictationController:
    """Orchestrates a single dictation session."""

    def __init__(
        self,
        audio_capture: AudioCapture,
        stt: STTService,
        text_processor: TextProcessor,
        text_output: TextOutput,
        ui: UIFeedback,
        metrics: MetricsSink,
    ):
        self._audio_capture = audio_capture
        self._stt = stt
        self._text_processor = text_processor
        self._text_output = text_output
        self._ui = ui
        self._metrics = metrics
        self._state = SessionStateMachine()
        self._cancel_token = CancelToken()

    def stop(self) -> None:
        """Stop recording and proceed to processing."""
        self._audio_capture.stop()
        self._state.transition(SessionEvent.STOP)

    def cancel(self) -> None:
        """Cancel recording and discard audio."""
        self._cancel_token.cancel()
        self._audio_capture.cancel()
        self._state.transition(SessionEvent.CANCEL)

    def run_session(
        self,
        mode,
        session: SessionContext,
        mode_names: dict,
        pre_output: callable | None = None,
    ) -> tuple[bool, object | None]:
        """Run one dictation session.

        Args:
            mode: ProcessingMode-like value.
            session: SessionContext with selected text + app context.
            mode_names: Mapping of mode to user-facing name.
            pre_output: Optional callback invoked right before output.
        """
        tracker = self._metrics
        mode_name = mode_names.get(mode, "Recording")

        # Start metrics
        tracker.start_session()
        self._cancel_token.reset()
        self._state.transition(SessionEvent.START)

        # Notify start
        self._ui.notify(
            f"🎤 {mode_name}",
            "Speak your instruction..." if session.selected_text else "Press FN to stop",
        )

        # Record
        with tracker.measure("audio_capture", mode=getattr(mode, "name", str(mode))):
            audio = self._audio_capture.record()

        self._state.transition(SessionEvent.STOP)

        if self._cancel_token.cancelled:
            self._state.transition(SessionEvent.CANCEL)
            return False, tracker.end_session()

        if audio is None or len(audio) == 0:
            print("No audio captured")
            self._state.transition(SessionEvent.ERROR)
            metrics_session = tracker.end_session()
            self._state.transition(SessionEvent.RESET)
            return False, metrics_session

        print("⏳ Processing...")

        # Transcribe
        with tracker.measure("stt_transcription"):
            text = self._stt.transcribe(audio)

        if not text:
            self._ui.notify("⚠ No speech", "Try again")
            print("No speech detected")
            self._state.transition(SessionEvent.ERROR)
            metrics_session = tracker.end_session()
            self._state.transition(SessionEvent.RESET)
            return False, metrics_session

        # Process text
        with tracker.measure("text_processing", mode=getattr(mode, "name", str(mode))):
            result = self._text_processor.process(
                text,
                mode,
                selected_text=session.selected_text,
                context=session.context,
            )

        if not result:
            print("Processing failed")
            self._ui.notify("⚠ Processing failed", "Check logs")
            self._state.transition(SessionEvent.ERROR)
            metrics_session = tracker.end_session()
            self._state.transition(SessionEvent.RESET)
            return False, metrics_session

        self._state.transition(SessionEvent.PROCESS_DONE)

        if pre_output:
            pre_output()

        # Output result
        with tracker.measure("text_output"):
            self._text_output.output(
                result,
                mode,
                replace_selection=session.selected_text is not None,
                context=session.context,
            )

        self._state.transition(SessionEvent.OUTPUT_DONE)
        return True, tracker.end_session()
