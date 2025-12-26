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

            # For Act on Text, check selection first
            selected_text = None
            if mode == ProcessingMode.ACT_ON_TEXT:
                selected_text = self._get_selection_for_act_on_text()
                if not selected_text:
                    return  # Already notified user

            notify(f"🎤 {mode_name}", "Press FN to stop")

            # Record until stopped
            audio = self.recognizer.record()

            if audio is None or len(audio) == 0:
                print("No audio captured")
                return

            print("⏳ Processing...")
            text = self.recognizer.transcribe(audio)

            if not text:
                print("No speech detected")
                notify("⚠ No speech", "Try again")
                return

            # Route to appropriate processor based on mode
            result = self._process_text(text, mode, selected_text)

            if result:
                self._output_result(result, mode, selected_text is not None)
            else:
                print("Processing failed")
                notify("⚠ Processing failed", "Check logs")

        except Exception as e:
            print(f"Error: {e}")
            notify("❌ Error", str(e)[:50])
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
            # Basic mode may have filler removal if enabled
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

        # Try to initialize FN key handler
        self._use_fn_key = self._init_fn_handler()

        if self._use_fn_key:
            print("Hotkey: FN key (hold=PTT, double-tap=toggle)")
            print("Modes: FN+Space=Act on Text, FN+Ctrl=Translate")
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


def main():
    app = Dicton()

    def signal_handler(sig, frame):
        app.request_shutdown()

    signal.signal(signal.SIGINT, signal_handler)
    if not IS_WINDOWS:
        signal.signal(signal.SIGTERM, signal_handler)

    app.run()


if __name__ == "__main__":
    main()
