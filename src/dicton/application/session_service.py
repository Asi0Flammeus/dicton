"""Application-level session orchestration."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from ..config import config
from ..core.controller import SessionContext
from ..processing_mode import ProcessingMode, get_mode_color, is_mode_enabled

if TYPE_CHECKING:
    from ..context_detector import ContextInfo


class SessionService:
    """Coordinate dictation session policy around the core controller."""

    def __init__(self, controller, keyboard, metrics, app_config):
        self._controller = controller
        self._keyboard = keyboard
        self._metrics = metrics
        self._app_config = app_config
        self._recording = False
        self._record_thread: threading.Thread | None = None
        self._current_mode = ProcessingMode.BASIC
        self._visualizer = None
        self._selected_text: str | None = None
        self._current_context: ContextInfo | None = None

    def bind_controller(self, controller) -> None:
        """Attach the session pipeline controller after service construction."""
        self._controller = controller

    @property
    def recording(self) -> bool:
        return self._recording

    def toggle_basic_recording(self) -> None:
        """Legacy toggle used by the modifier+key keyboard listener."""
        if self._recording:
            self.stop_recording()
        else:
            self.start_recording(ProcessingMode.BASIC)

    def start_recording(self, mode: ProcessingMode) -> None:
        """Start recording for the requested processing mode."""
        if self._recording:
            return

        if self._record_thread is not None and self._record_thread.is_alive():
            return  # Previous session still processing

        if not is_mode_enabled(mode):
            mode = ProcessingMode.BASIC

        self._current_mode = mode
        self._selected_text = None
        self._current_context = None

        if self._app_config.context_enabled:
            try:
                from ..context_detector import get_context_detector

                detector = get_context_detector()
                if detector:
                    self._current_context = detector.get_context()
            except Exception as exc:
                if self._app_config.context_debug:
                    print(f"[Context] Detection failed: {exc}")

        if mode == ProcessingMode.ACT_ON_TEXT:
            selected = self._capture_selection_for_act_on_text()
            if not selected:
                return
            self._selected_text = selected
            print(
                f"📋 Selected: {selected[:50]}..."
                if len(selected) > 50
                else f"📋 Selected: {selected}"
            )

        self._recording = True
        self._update_visualizer_color(mode)
        self._record_thread = threading.Thread(target=self._record_and_transcribe, daemon=True)
        self._record_thread.start()

    def stop_recording(self) -> None:
        """Stop recording and continue to processing."""
        if not self._recording:
            return

        print("⏹ Stopping...")
        self._controller.stop()
        self._recording = False

    def cancel_recording(self) -> None:
        """Cancel recording and discard captured audio."""
        if not self._recording:
            return

        if self._app_config.debug:
            print("⏹ Cancelled (tap)")
        self._controller.cancel()
        self._recording = False

    def _update_visualizer_color(self, mode: ProcessingMode) -> None:
        try:
            if self._visualizer is None:
                from ..visualizer import get_visualizer

                self._visualizer = get_visualizer()

            self._visualizer.set_colors(get_mode_color(mode))
        except Exception:
            pass

    def _record_and_transcribe(self) -> None:
        mode = self._current_mode
        tracker = self._metrics
        mode_names = {
            ProcessingMode.BASIC: "Recording",
            ProcessingMode.ACT_ON_TEXT: "Act on Text",
            ProcessingMode.REFORMULATION: "Reformulation",
            ProcessingMode.TRANSLATION: "Translation",
            ProcessingMode.TRANSLATE_REFORMAT: "Translate+Reformat",
            ProcessingMode.RAW: "Raw Mode",
        }
        viz = self._load_visualizer()

        try:
            selected_text = None
            if mode == ProcessingMode.ACT_ON_TEXT:
                selected_text = self._selected_text
                if not selected_text:
                    print("⚠ No selection captured")
                    return

            session_ctx = SessionContext(
                selected_text=selected_text,
                context=self._current_context,
            )

            def _pre_output() -> None:
                nonlocal viz
                if viz:
                    viz.stop()
                    viz = None

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
            from ..ui_feedback import notify

            notify("❌ Error", str(exc)[:50])
            try:
                tracker.end_session()
            except Exception:
                pass
        finally:
            self._recording = False
            if viz:
                viz.stop()

    def _load_visualizer(self):
        viz = None
        try:
            if config.VISUALIZER_BACKEND == "gtk":
                try:
                    from ..visualizer_gtk import get_visualizer

                    viz = get_visualizer()
                except ImportError:
                    from ..visualizer import get_visualizer

                    viz = get_visualizer()
            elif config.VISUALIZER_BACKEND == "vispy":
                try:
                    from ..visualizer_vispy import get_visualizer

                    viz = get_visualizer()
                except ImportError:
                    from ..visualizer import get_visualizer

                    viz = get_visualizer()
            else:
                from ..visualizer import get_visualizer

                viz = get_visualizer()
        except Exception:
            viz = None
        return viz

    def _capture_selection_for_act_on_text(self) -> str | None:
        try:
            from ..platform_utils import IS_WAYLAND
            from ..selection_handler import get_primary_selection, has_selection

            if not has_selection():
                print("⚠ No text selected")
                from ..ui_feedback import notify

                notify("⚠ No Selection", "Highlight text first, then press FN+Shift")
                return None

            selected = get_primary_selection()
            if not selected:
                tool_hint = "wl-clipboard" if IS_WAYLAND else "xclip"
                print(f"⚠ Could not read selection (install {tool_hint})")
                from ..ui_feedback import notify

                notify("⚠ Selection Error", f"Install {tool_hint}")
                return None

            return selected

        except ImportError as exc:
            print(f"⚠ Selection handler not available: {exc}")
            from ..ui_feedback import notify

            notify("⚠ Not Available", "Install xclip or wl-clipboard")
            return None

    def process_text(
        self,
        text: str,
        mode: ProcessingMode,
        selected_text: str | None = None,
        context: ContextInfo | None = None,
    ) -> str | None:
        """Process transcribed text based on the current mode."""
        if not is_mode_enabled(mode):
            mode = ProcessingMode.BASIC

        if mode in (ProcessingMode.BASIC, ProcessingMode.RAW):
            return text

        try:
            from .. import llm_processor

            if not llm_processor.is_available():
                print("⚠ LLM not available (set GEMINI_API_KEY or ANTHROPIC_API_KEY)")
                from ..ui_feedback import notify

                notify("⚠ LLM Not Available", "Configure LLM_PROVIDER")
                return text

            if mode == ProcessingMode.ACT_ON_TEXT and selected_text:
                return llm_processor.act_on_text(selected_text, text, context=context)
            if mode == ProcessingMode.REFORMULATION:
                if config.ENABLE_REFORMULATION:
                    return llm_processor.reformulate(text, context=context)
                return self._filter_fillers_local(text)
            if mode == ProcessingMode.TRANSLATION:
                return llm_processor.translate(text, "English", context=context)
            if mode == ProcessingMode.TRANSLATE_REFORMAT:
                translated = llm_processor.translate(text, "English", context=context)
                if translated:
                    return llm_processor.reformulate(translated, context=context)
                return None
        except ImportError:
            print("⚠ LLM processor not available")
            return text

        return text

    def output_result(
        self,
        text: str,
        mode: ProcessingMode,
        replace_selection: bool,
        context: ContextInfo | None = None,
    ) -> None:
        """Emit processed text to the active application."""
        typing_delay_ms = 50

        if context:
            from ..context_profiles import get_profile_manager

            manager = get_profile_manager()
            profile = manager.match_context(context)
            if profile:
                typing_delay_ms = int(manager.get_typing_delay(profile) * 1000)
                if self._app_config.context_debug:
                    print(f"[Context] Typing delay: {typing_delay_ms}ms ({profile.typing_speed})")

        self._keyboard.insert_text(text, typing_delay_ms=typing_delay_ms)

        if mode == ProcessingMode.ACT_ON_TEXT:
            print(f"✓ Replaced: {text[:50]}..." if len(text) > 50 else f"✓ {text}")
            from ..ui_feedback import notify

            notify("✓ Text Replaced", text[:100])
        else:
            print(f"✓ {text[:50]}..." if len(text) > 50 else f"✓ {text}")
            from ..ui_feedback import notify

            notify("✓ Done", text[:100])

    def _filter_fillers_local(self, text: str) -> str:
        try:
            from ..text_processor import filter_filler_words

            return filter_filler_words(text)
        except ImportError:
            return text
