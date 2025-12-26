#!/usr/bin/env python3
"""Dicton: Voice-to-text with FN key activation and processing modes"""

import os
import signal
import threading
import warnings

# Suppress warnings
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
warnings.filterwarnings("ignore")

from .config import config
from .keyboard_handler import KeyboardHandler
from .latency_tracker import get_latency_tracker
from .platform_utils import IS_LINUX, IS_WINDOWS
from .processing_mode import ProcessingMode, get_mode_color
from .speech_recognition_engine import SpeechRecognizer
from .ui_feedback import notify


class Dicton:
    """Main application with FN key hotkey and processing modes"""

    def __init__(self):
        config.create_dirs()
        self.recognizer = SpeechRecognizer()
        self.keyboard = KeyboardHandler(self._legacy_toggle)
        self.recording = False
        self.record_thread = None
        self._shutdown_event = threading.Event()
        self._current_mode = ProcessingMode.BASIC
        self._visualizer = None

        # FN key handler (Linux only, requires evdev)
        self._fn_handler = None
        self._use_fn_key = False

    def _init_fn_handler(self) -> bool:
        """Initialize FN key handler if available"""
        if not IS_LINUX:
            return False

        if config.HOTKEY_BASE.lower() != "fn":
            return False

        try:
            from .fn_key_handler import FnKeyHandler

            self._fn_handler = FnKeyHandler(
                on_start_recording=self._on_start_recording,
                on_stop_recording=self._on_stop_recording,
                on_cancel_recording=self._on_cancel_recording,
            )
            return self._fn_handler.start()
        except ImportError:
            print("FN key support requires evdev: pip install dicton[fnkey]")
            return False
        except Exception as e:
            if config.DEBUG:
                print(f"FN handler init failed: {e}")
            return False

    def _legacy_toggle(self):
        """Legacy toggle for Alt+G hotkey (backward compatibility)"""
        if self.recording:
            self._on_stop_recording()
        else:
            self._on_start_recording(ProcessingMode.BASIC)

    def _on_start_recording(self, mode: ProcessingMode):
        """Start recording with specified processing mode"""
        if self.recording:
            return

        self._current_mode = mode
        self.recording = True

        # Update visualizer color based on mode
        self._update_visualizer_color(mode)

        # Start recording thread
        self.record_thread = threading.Thread(
            target=self._record_and_transcribe, daemon=True
        )
        self.record_thread.start()

    def _on_stop_recording(self):
        """Stop recording (will process audio)"""
        if not self.recording:
            return

        print("⏹ Stopping...")
        self.recognizer.stop()
        self.recording = False

    def _on_cancel_recording(self):
        """Cancel recording (tap detected, discard audio)"""
        if not self.recording:
            return

        if config.DEBUG:
            print("⏹ Cancelled (tap)")
        self.recognizer.cancel()
        self.recording = False

    def _update_visualizer_color(self, mode: ProcessingMode):
        """Update visualizer ring color for current mode"""
        try:
            if self._visualizer is None:
                from .visualizer import get_visualizer
                self._visualizer = get_visualizer()

            color = get_mode_color(mode)
            self._visualizer.set_colors(color)
        except Exception:
            pass  # Visualizer not critical

    def _record_and_transcribe(self):
        """Record audio and process based on current mode"""
        mode = self._current_mode
        tracker = get_latency_tracker()
        mode_names = {
            ProcessingMode.BASIC: "Recording",
            ProcessingMode.ACT_ON_TEXT: "Act on Text",
            ProcessingMode.REFORMULATION: "Reformulation",
            ProcessingMode.TRANSLATION: "Translation",
            ProcessingMode.TRANSLATE_REFORMAT: "Translate+Reformat",
            ProcessingMode.RAW: "Raw Mode",
        }

        try:
            mode_name = mode_names.get(mode, "Recording")

            # Start latency tracking session
            tracker.start_session()

            # For Act on Text, check selection first
            selected_text = None
            if mode == ProcessingMode.ACT_ON_TEXT:
                selected_text = self._get_selection_for_act_on_text()
                if not selected_text:
                    tracker.end_session()
                    return  # Already notified user

            notify(f"🎤 {mode_name}", "Press FN to stop")

            # Record until stopped
            with tracker.measure("audio_capture", mode=mode.name):
                audio = self.recognizer.record()

            if audio is None or len(audio) == 0:
                print("No audio captured")
                tracker.end_session()
                return

            print("⏳ Processing...")

            # Transcribe audio
            with tracker.measure("stt_transcription"):
                text = self.recognizer.transcribe(audio)

            if not text:
                print("No speech detected")
                notify("⚠ No speech", "Try again")
                tracker.end_session()
                return

            # Route to appropriate processor based on mode
            with tracker.measure("text_processing", mode=mode.name):
                result = self._process_text(text, mode, selected_text)

            if result:
                with tracker.measure("text_output"):
                    self._output_result(result, mode, selected_text is not None)
            else:
                print("Processing failed")
                notify("⚠ Processing failed", "Check logs")

            # End session and log
            session = tracker.end_session()
            if config.DEBUG and session:
                total_ms = session.total_duration_ms()
                print(f"⏱ Total latency: {total_ms:.0f}ms")

        except Exception as e:
            print(f"Error: {e}")
            notify("❌ Error", str(e)[:50])
            tracker.end_session()
        finally:
            self.recording = False

    def _get_selection_for_act_on_text(self) -> str | None:
        """Get selected text for Act on Text mode"""
        try:
            from .selection_handler import get_primary_selection, has_selection

            if not has_selection():
                print("⚠ No text selected")
                notify("⚠ No Selection", "Highlight text first")
                self.recording = False
                return None

            selected = get_primary_selection()
            if not selected:
                print("⚠ Could not read selection")
                notify("⚠ Selection Error", "Try selecting again")
                self.recording = False
                return None

            return selected

        except ImportError:
            print("⚠ Selection handler not available")
            notify("⚠ Not Available", "Install xclip")
            self.recording = False
            return None

    def _process_text(
        self, text: str, mode: ProcessingMode, selected_text: str | None = None
    ) -> str | None:
        """Process transcribed text based on mode"""

        if mode == ProcessingMode.RAW:
            # No processing, return as-is
            return text

        if mode == ProcessingMode.BASIC:
            # Basic mode uses LLM reformulation by default (cleaner output)
            try:
                from . import llm_processor

                if config.ENABLE_REFORMULATION and llm_processor.is_available():
                    return llm_processor.reformulate(text)
            except ImportError:
                pass
            # Fallback to local filler removal if LLM not available
            if config.FILTER_FILLERS:
                return self._filter_fillers_local(text)
            return text

        # LLM-powered modes
        try:
            from . import llm_processor

            if not llm_processor.is_available():
                print("⚠ LLM not available (check GEMINI_API_KEY)")
                notify("⚠ LLM Not Available", "Set GEMINI_API_KEY")
                return text  # Fallback to raw text

            if mode == ProcessingMode.ACT_ON_TEXT and selected_text:
                return llm_processor.act_on_text(selected_text, text)

            elif mode == ProcessingMode.REFORMULATION:
                # Check if LLM reformulation is enabled
                if config.ENABLE_REFORMULATION:
                    return llm_processor.reformulate(text)
                else:
                    # Fallback to local filler removal only
                    return self._filter_fillers_local(text)

            elif mode == ProcessingMode.TRANSLATION:
                return llm_processor.translate(text, "English")

            elif mode == ProcessingMode.TRANSLATE_REFORMAT:
                # Translate first, then reformulate
                translated = llm_processor.translate(text, "English")
                if translated:
                    return llm_processor.reformulate(translated)
                return None

        except ImportError:
            print("⚠ LLM processor not available")
            return text

        return text

    def _filter_fillers_local(self, text: str) -> str:
        """Local filler word removal (no LLM)"""
        try:
            from .text_processor import filter_filler_words
            return filter_filler_words(text)
        except ImportError:
            return text

    def _output_result(self, text: str, mode: ProcessingMode, replace_selection: bool):
        """Output the processed text"""
        if replace_selection and mode == ProcessingMode.ACT_ON_TEXT:
            # Replace selected text with result
            success = self.keyboard.replace_selection_with_text(text)
            if success:
                print(f"✓ Replaced: {text[:50]}..." if len(text) > 50 else f"✓ {text}")
                notify("✓ Text Replaced", text[:100])
            else:
                # Fallback to insert
                self.keyboard.insert_text(text)
                print(f"✓ Inserted: {text[:50]}..." if len(text) > 50 else f"✓ {text}")
                notify("✓ Done", text[:100])
        else:
            # Normal text insertion
            self.keyboard.insert_text(text)
            print(f"✓ {text[:50]}..." if len(text) > 50 else f"✓ {text}")
            notify("✓ Done", text[:100])

    def run(self):
        """Run the application"""
        print("\n" + "=" * 50)
        print("🚀 Dicton")
        print("=" * 50)

        # Check for updates in background (non-blocking)
        try:
            from .update_checker import check_for_updates_async

            check_for_updates_async()
        except ImportError:
            pass  # Update checker not critical

        # Try to initialize FN key handler
        self._use_fn_key = self._init_fn_handler()

        if self._use_fn_key:
            print("Hotkey: FN key (hold=PTT, double-tap=toggle)")
            print("Modes: FN+Ctrl=Translate, FN+Alt=Act on Text (toggle to start/stop)")
        else:
            print(f"Hotkey: {config.HOTKEY_MODIFIER}+{config.HOTKEY_KEY}")
            self.keyboard.start()

        stt_mode = "ElevenLabs" if self.recognizer.use_elevenlabs else "Local"
        print(f"STT: {stt_mode}")
        print("\nPress hotkey to start/stop recording")
        print("Press Ctrl+C to quit")
        print("=" * 50 + "\n")

        hotkey_display = "FN" if self._use_fn_key else f"{config.HOTKEY_MODIFIER}+{config.HOTKEY_KEY}"
        notify("Dicton Ready", f"Press {hotkey_display}")

        # Cross-platform wait loop
        try:
            if IS_WINDOWS:
                self._shutdown_event.wait()
            else:
                signal.pause()
        except KeyboardInterrupt:
            pass

        self.shutdown()

    def shutdown(self):
        """Clean shutdown"""
        print("\nShutting down...")
        self._shutdown_event.set()

        if self._fn_handler:
            self._fn_handler.stop()

        self.keyboard.stop()
        self.recognizer.cleanup()
        print("✓ Done")

    def request_shutdown(self):
        """Request application shutdown (thread-safe)"""
        self._shutdown_event.set()


def show_latency_report():
    """Show latency report from log file"""
    from .latency_tracker import LatencyTracker

    tracker = LatencyTracker(enabled=True)
    count = tracker.load_from_log()

    if count == 0:
        print("No latency data found.")
        print(f"Log file: {tracker.log_path}")
        print("\nRun dicton with DEBUG=true to collect latency data.")
        return

    print(f"\n📊 Dicton Latency Report ({count} sessions)")
    tracker.print_summary()
    print(f"\nLog file: {tracker.log_path}")


def clear_latency_log():
    """Clear the latency log file"""
    from .latency_tracker import LatencyTracker

    tracker = LatencyTracker(enabled=True)
    tracker.clear_log()
    print(f"✓ Cleared latency log: {tracker.log_path}")


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Dicton: Voice-to-text dictation tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Hotkeys (FN key mode):
  FN (hold)        Push-to-talk (with auto-reformulation)
  FN (double-tap)  Toggle recording (with auto-reformulation)
  FN + Ctrl        Translate to English (toggle: press to start/stop)
  FN + Shift       LLM Reformulation (toggle: press to start/stop)
  FN + Alt         Act on Text - apply instruction to selection (toggle)
  FN + Space       Raw mode - no processing (toggle)

Examples:
  dicton                  Start dictation service
  dicton --benchmark      Show latency statistics
  dicton --check-update   Check for new version
  dicton --clear-log      Clear latency history
""",
    )
    parser.add_argument(
        "--benchmark",
        action="store_true",
        help="Show latency report from previous sessions",
    )
    parser.add_argument(
        "--check-update",
        action="store_true",
        help="Check for available updates",
    )
    parser.add_argument(
        "--clear-log",
        action="store_true",
        help="Clear the latency log file",
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="Show version information",
    )

    args = parser.parse_args()

    if args.version:
        from . import __version__

        print(f"Dicton v{__version__}")
        return

    if args.check_update:
        from .update_checker import check_for_updates, print_update_notification

        print("Checking for updates...")
        update = check_for_updates(force=True)
        if update:
            print_update_notification(update)
        else:
            from . import __version__

            print(f"✓ You are running the latest version (v{__version__})")
        return

    if args.clear_log:
        clear_latency_log()
        return

    if args.benchmark:
        show_latency_report()
        return

    # Normal operation
    app = Dicton()

    def signal_handler(sig, frame):
        app.request_shutdown()

    signal.signal(signal.SIGINT, signal_handler)
    if not IS_WINDOWS:
        signal.signal(signal.SIGTERM, signal_handler)

    app.run()


if __name__ == "__main__":
    main()
