"""Application-level session orchestration."""

from __future__ import annotations

import logging
import threading
from typing import Any

from ..core.cancel_token import CancelToken
from ..core.processing_mode import ProcessingMode, get_mode_color, is_mode_enabled
from ..core.state_machine import SessionEvent, SessionState, SessionStateMachine

logger = logging.getLogger(__name__)


class _NullNotifications:
    def notify(self, title: str, message: str, timeout: int = 2) -> None:
        pass


class _NoopAudioSessionControl:
    def start_recording(self) -> None:
        return None

    def stop_recording(self) -> None:
        return None

    def cancel_recording(self) -> None:
        return None


class SessionService:
    """Coordinate a dictation session from recording through text output."""

    def __init__(
        self,
        *,
        recognizer,
        text_output,
        metrics,
        app_config,
        notification_service=None,
        llm_provider=None,
        visualizer_factory=None,
        chunk_manager=None,
        audio_control=None,
    ):
        self._recognizer = recognizer
        self._chunk_manager = chunk_manager
        self._audio_control = audio_control or _NoopAudioSessionControl()
        self._text_output = text_output
        self._metrics = metrics
        self._notifications = (
            notification_service if notification_service is not None else _NullNotifications()
        )
        self._llm = llm_provider
        self._get_visualizer = (
            visualizer_factory if visualizer_factory is not None else lambda: None
        )
        self._app_config = app_config
        self._session_lock = threading.Lock()
        self._starting = False
        self._recording = False
        self._record_thread: threading.Thread | None = None
        self._current_mode = ProcessingMode.BASIC
        self._visualizer = None
        self._state = SessionStateMachine()
        self._cancel_token = CancelToken()

    def add_state_observer(self, callback) -> None:
        """Register an observer on the session pipeline state machine."""
        self._state.add_observer(callback)

    @property
    def recording(self) -> bool:
        with self._session_lock:
            return self._recording

    def toggle_basic_recording(self) -> None:
        """Legacy toggle used by the modifier+key keyboard listener."""
        if self._recording:
            self.stop_recording()
        else:
            self.start_recording(ProcessingMode.BASIC)

    def start_recording(self, mode: ProcessingMode) -> None:
        """Start recording for the requested processing mode."""
        with self._session_lock:
            if self._starting or self._recording:
                return
            if self._record_thread is not None and self._record_thread.is_alive():
                return  # Previous session still processing
            self._starting = True

        if not is_mode_enabled(mode, self._app_config.enable_advanced_modes):
            mode = ProcessingMode.BASIC

        try:
            self._update_visualizer_color(mode)

            record_thread = threading.Thread(
                target=self._record_and_transcribe,
                args=(mode,),
                daemon=True,
            )
            with self._session_lock:
                self._current_mode = mode
                self._recording = True
                self._record_thread = record_thread
                self._starting = False
            record_thread.start()
        finally:
            with self._session_lock:
                self._starting = False

    def stop_recording(self) -> None:
        """Stop recording and continue to processing."""
        with self._session_lock:
            if not self._recording:
                return
            self._recording = False

        print("⏹ Stopping...")
        self._recognizer.stop()
        self._state.transition(SessionEvent.STOP)

    def cancel_recording(self) -> None:
        """Cancel the active recording/processing session and discard pending work."""
        with self._session_lock:
            active = self._recording or (
                self._record_thread is not None and self._record_thread.is_alive()
            )
            if not active:
                return
            self._recording = False

        if self._app_config.debug:
            print("⏹ Cancelled (tap)")
        self._cancel_token.cancel()
        self._recognizer.cancel()
        if self._chunk_manager:
            self._chunk_manager.cancel()
        self._audio_control.cancel_recording()
        self._state.transition(SessionEvent.CANCEL)

    def _update_visualizer_color(self, mode: ProcessingMode) -> None:
        try:
            if self._visualizer is None:
                self._visualizer = self._get_visualizer()

            if self._visualizer:
                self._visualizer.set_colors(get_mode_color(mode))
        except Exception:
            pass

    def _record_audio(self):
        if self._chunk_manager:
            self._chunk_manager.start_session()
            return self._recognizer.record(on_chunk=self._chunk_manager.feed_chunk)
        return self._recognizer.record()

    def _transcribe_audio(self, audio) -> str | None:
        if self._chunk_manager:
            result = self._chunk_manager.finalize()
            if result.is_partial:
                logger.warning(
                    "Partial transcription: %d/%d chunks failed",
                    result.failed_chunks,
                    result.total_chunks,
                )
            return self._recognizer.filter_text(result.text) if result.text else None
        return self._recognizer.transcribe(audio)

    def _audio_is_empty(self, audio) -> bool:
        if audio is None:
            return True
        try:
            return len(audio) == 0
        except TypeError:
            return False

    def _finish_cancelled_session(self, tracker):
        if self._state.state is not SessionState.IDLE:
            self._state.transition(SessionEvent.CANCEL)
        return tracker.end_session()

    def _record_and_transcribe(self, mode: ProcessingMode) -> None:
        tracker = self._metrics
        mode_names = {
            ProcessingMode.BASIC: "Recording",
            ProcessingMode.REFORMULATION: "Reformulation",
            ProcessingMode.TRANSLATION: "Translation",
            ProcessingMode.TRANSLATE_REFORMAT: "Translate+Reformat",
            ProcessingMode.RAW: "Raw Mode",
        }
        mode_name = mode_names.get(mode, "Recording")
        if self._visualizer is None:
            self._visualizer = self._get_visualizer()
        viz = self._visualizer

        try:
            tracker.start_session()
            self._cancel_token.reset()
            self._state.transition(SessionEvent.START)

            self._notifications.notify(f"🎤 {mode_name}", "Press FN to stop")

            with tracker.measure("audio_capture", mode=getattr(mode, "name", str(mode))):
                self._audio_control.start_recording()
                try:
                    audio = self._record_audio()
                finally:
                    self._audio_control.stop_recording()

            if self._cancel_token.cancelled:
                self._finish_cancelled_session(tracker)
                return

            if self._state.state == SessionState.RECORDING:
                self._state.transition(SessionEvent.STOP)

            if self._audio_is_empty(audio):
                print("No audio captured")
                self._state.transition(SessionEvent.ERROR)
                session = tracker.end_session()
                self._state.transition(SessionEvent.RESET)
                self._print_debug_latency(session)
                return

            print("⏳ Processing...")

            with tracker.measure("stt_transcription"):
                text = self._transcribe_audio(audio)

            if self._cancel_token.cancelled:
                self._finish_cancelled_session(tracker)
                return

            if not text:
                self._notifications.notify("⚠ No speech", "Try again")
                print("No speech detected")
                self._state.transition(SessionEvent.ERROR)
                session = tracker.end_session()
                self._state.transition(SessionEvent.RESET)
                self._print_debug_latency(session)
                return

            with tracker.measure("text_processing", mode=getattr(mode, "name", str(mode))):
                result = self.process_text(text, mode, selected_text=None)

            if self._cancel_token.cancelled:
                self._finish_cancelled_session(tracker)
                return

            if not result:
                print("Processing failed")
                self._notifications.notify("⚠ Processing failed", "Check logs")
                self._state.transition(SessionEvent.ERROR)
                session = tracker.end_session()
                self._state.transition(SessionEvent.RESET)
                self._print_debug_latency(session)
                return

            self._state.transition(SessionEvent.PROCESS_DONE)

            if viz:
                viz.stop()

            with tracker.measure("text_output"):
                self.output_result(result, mode)

            self._state.transition(SessionEvent.OUTPUT_DONE)
            self._print_debug_latency(tracker.end_session())

        except Exception as exc:
            self._state.transition(SessionEvent.ERROR)
            self._state.transition(SessionEvent.RESET)
            print(f"Error: {exc}")
            self._notifications.notify("❌ Error", str(exc)[:50])
            try:
                tracker.end_session()
            except Exception:
                pass
        finally:
            with self._session_lock:
                self._recording = False
                if self._record_thread is threading.current_thread():
                    self._record_thread = None
            if viz:
                viz.stop()

    def _print_debug_latency(self, session: Any) -> None:
        if self._app_config.debug and session:
            total_ms = session.total_duration_ms()
            print(f"⏱ Total latency: {total_ms:.0f}ms")

    def process_text(
        self,
        text: str,
        mode: ProcessingMode,
        selected_text: str | None = None,
    ) -> str | None:
        """Process transcribed text based on the current mode."""
        if not is_mode_enabled(mode, self._app_config.enable_advanced_modes):
            mode = ProcessingMode.BASIC

        if mode in (ProcessingMode.BASIC, ProcessingMode.RAW):
            return text

        if self._llm is None or not self._llm.is_available():
            print("⚠ LLM not available (set GEMINI_API_KEY or ANTHROPIC_API_KEY)")
            self._notifications.notify("⚠ LLM Not Available", "Configure LLM_PROVIDER")
            return text

        from ..adapters.llm.prompts import reformulate, translate

        llm_kwargs = {
            "user_provider": self._app_config.llm_provider,
            "debug": self._app_config.debug,
        }

        if mode == ProcessingMode.REFORMULATION:
            if self._app_config.enable_reformulation:
                return reformulate(text, **llm_kwargs)
            return self._filter_fillers_local(text)
        if mode == ProcessingMode.TRANSLATION:
            return translate(text, "English", **llm_kwargs)
        if mode == ProcessingMode.TRANSLATE_REFORMAT:
            translated = translate(text, "English", **llm_kwargs)
            if translated:
                return reformulate(translated, **llm_kwargs)
            return None

        return text

    def output_result(self, text: str, mode: ProcessingMode) -> None:
        """Emit processed text to the active application."""
        self._text_output.insert_text(text, delay_ms=50)
        print(f"✓ {text[:50]}..." if len(text) > 50 else f"✓ {text}")
        self._notifications.notify("✓ Done", text[:100])

    def _filter_fillers_local(self, text: str) -> str:
        try:
            from ..adapters.text.processor import filter_filler_words

            return filter_filler_words(text)
        except ImportError:
            return text
