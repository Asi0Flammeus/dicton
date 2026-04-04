"""Application-level session orchestration."""

from __future__ import annotations

import threading

from ..core.controller import SessionContext
from ..shared.processing_mode import ProcessingMode, get_mode_color, is_mode_enabled


class _NullNotifications:
    def notify(self, title: str, message: str, timeout: int = 2) -> None:
        pass


class SessionService:
    """Coordinate dictation session policy around the core controller."""

    def __init__(
        self,
        controller,
        text_output,
        metrics,
        app_config,
        selection_reader=None,
        notification_service=None,
        llm_provider=None,
        visualizer_factory=None,
    ):
        self._controller = controller
        self._text_output = text_output
        self._metrics = metrics
        self._selection = selection_reader
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
        self._selected_text: str | None = None

    def bind_controller(self, controller) -> None:
        """Attach the session pipeline controller after service construction."""
        self._controller = controller

    def add_state_observer(self, callback) -> None:
        """Register an observer on the session pipeline state machine."""
        self._controller._state.add_observer(callback)

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

        if not is_mode_enabled(mode):
            mode = ProcessingMode.BASIC

        selected_text = None

        try:
            if mode == ProcessingMode.ACT_ON_TEXT:
                selected = self._capture_selection_for_act_on_text()
                if not selected:
                    return
                selected_text = selected
                print(
                    f"📋 Selected: {selected[:50]}..."
                    if len(selected) > 50
                    else f"📋 Selected: {selected}"
                )

            self._update_visualizer_color(mode)

            record_thread = threading.Thread(
                target=self._record_and_transcribe,
                args=(mode, selected_text),
                daemon=True,
            )
            with self._session_lock:
                self._current_mode = mode
                self._selected_text = selected_text
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
        self._controller.stop()

    def cancel_recording(self) -> None:
        """Cancel recording and discard captured audio."""
        with self._session_lock:
            if not self._recording:
                return
            self._recording = False

        if self._app_config.debug:
            print("⏹ Cancelled (tap)")
        self._controller.cancel()

    def _update_visualizer_color(self, mode: ProcessingMode) -> None:
        try:
            if self._visualizer is None:
                self._visualizer = self._get_visualizer()

            if self._visualizer:
                self._visualizer.set_colors(get_mode_color(mode))
        except Exception:
            pass

    def _record_and_transcribe(
        self,
        mode: ProcessingMode,
        selected_text: str | None,
    ) -> None:
        tracker = self._metrics
        mode_names = {
            ProcessingMode.BASIC: "Recording",
            ProcessingMode.ACT_ON_TEXT: "Act on Text",
            ProcessingMode.REFORMULATION: "Reformulation",
            ProcessingMode.TRANSLATION: "Translation",
            ProcessingMode.TRANSLATE_REFORMAT: "Translate+Reformat",
            ProcessingMode.RAW: "Raw Mode",
        }
        if self._visualizer is None:
            self._visualizer = self._get_visualizer()
        viz = self._visualizer

        try:
            if mode == ProcessingMode.ACT_ON_TEXT:
                if not selected_text:
                    print("⚠ No selection captured")
                    return

            session_ctx = SessionContext(
                selected_text=selected_text,
            )

            def _pre_output() -> None:
                if viz:
                    viz.stop()

            success, session = self._controller.run_session(
                mode=mode,
                session=session_ctx,
                mode_names=mode_names,
                pre_output=_pre_output,
            )
            if not success:
                return

            if self._app_config.debug and session:
                total_ms = session.total_duration_ms()
                print(f"⏱ Total latency: {total_ms:.0f}ms")

        except Exception as exc:
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

    def _capture_selection_for_act_on_text(self) -> str | None:
        if self._selection is None:
            print("⚠ Selection reader not configured")
            self._notifications.notify("⚠ Not Available", "Install xclip or wl-clipboard")
            return None

        if not self._selection.has_selection():
            print("⚠ No text selected")
            self._notifications.notify(
                "⚠ No Selection", "Highlight text first, then press FN+Shift"
            )
            return None

        selected = self._selection.get_selection()
        if not selected:
            print("⚠ Could not read selection")
            self._notifications.notify("⚠ Selection Error", "Install xclip or wl-clipboard")
            return None

        return selected

    def process_text(
        self,
        text: str,
        mode: ProcessingMode,
        selected_text: str | None = None,
    ) -> str | None:
        """Process transcribed text based on the current mode."""
        if not is_mode_enabled(mode):
            mode = ProcessingMode.BASIC

        if mode in (ProcessingMode.BASIC, ProcessingMode.RAW):
            return text

        if self._llm is None or not self._llm.is_available():
            print("⚠ LLM not available (set GEMINI_API_KEY or ANTHROPIC_API_KEY)")
            self._notifications.notify("⚠ LLM Not Available", "Configure LLM_PROVIDER")
            return text

        from ..adapters.llm.prompts import act_on_text, reformulate, translate
        from ..shared.config import config

        llm_kwargs = {"user_provider": config.LLM_PROVIDER, "debug": config.DEBUG}

        if mode == ProcessingMode.ACT_ON_TEXT and selected_text:
            return act_on_text(selected_text, text, **llm_kwargs)
        if mode == ProcessingMode.REFORMULATION:
            if config.ENABLE_REFORMULATION:
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

    def output_result(
        self,
        text: str,
        mode: ProcessingMode,
        replace_selection: bool,
    ) -> None:
        """Emit processed text to the active application."""
        self._text_output.insert_text(text, delay_ms=50)

        if mode == ProcessingMode.ACT_ON_TEXT:
            print(f"✓ Replaced: {text[:50]}..." if len(text) > 50 else f"✓ {text}")
            self._notifications.notify("✓ Text Replaced", text[:100])
        else:
            print(f"✓ {text[:50]}..." if len(text) > 50 else f"✓ {text}")
            self._notifications.notify("✓ Done", text[:100])

    def _filter_fillers_local(self, text: str) -> str:
        try:
            from ..shared.text_processor import filter_filler_words

            return filter_filler_words(text)
        except ImportError:
            return text
