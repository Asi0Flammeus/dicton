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
from .context_detector import ContextInfo, get_context_detector
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

        # Warn prominently if no STT provider is available
        if not self.recognizer._provider_available:
            print("❌ No STT provider configured - dictation will not work!")

        self.keyboard = KeyboardHandler(self._legacy_toggle)
        self.recording = False
        self.record_thread = None
        self._shutdown_event = threading.Event()
        self._current_mode = ProcessingMode.BASIC
        self._visualizer = None
        self._selected_text = None  # For Act on Text mode
        self._current_context: ContextInfo | None = None  # Context at recording start

        # FN key handler (Linux only, requires evdev)
        self._fn_handler = None
        self._use_fn_key = False

    def _init_fn_handler(self) -> bool:
        """Initialize FN key handler if available.

        Supports both FN key mode and custom hotkey mode (e.g., alt+g).
        """
        if not IS_LINUX:
            return False

        hotkey_base = config.HOTKEY_BASE.lower()
        # Only use FnKeyHandler for "fn" or "custom" modes
        # Other values fall back to legacy pynput-based keyboard handler
        if hotkey_base not in ("fn", "custom"):
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
        self._selected_text = None  # Reset selected text
        self._current_context = None  # Reset context

        # Detect context at recording start (not on every frame)
        if config.CONTEXT_ENABLED:
            try:
                detector = get_context_detector()
                if detector:
                    self._current_context = detector.get_context()
            except Exception as e:
                if config.CONTEXT_DEBUG:
                    print(f"[Context] Detection failed: {e}")

        # For Act on Text, capture selection BEFORE starting recording
        if mode == ProcessingMode.ACT_ON_TEXT:
            selected = self._capture_selection_for_act_on_text()
            if not selected:
                return  # Already notified user, don't start recording
            self._selected_text = selected
            print(f"📋 Selected: {selected[:50]}..." if len(selected) > 50 else f"📋 Selected: {selected}")

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

        # Get visualizer reference (use same import logic as speech_recognition_engine)
        viz = None
        try:
            if config.VISUALIZER_BACKEND == "gtk":
                try:
                    from .visualizer_gtk import get_visualizer
                    viz = get_visualizer()
                except ImportError:
                    from .visualizer import get_visualizer
                    viz = get_visualizer()
            elif config.VISUALIZER_BACKEND == "vispy":
                try:
                    from .visualizer_vispy import get_visualizer
                    viz = get_visualizer()
                except ImportError:
                    from .visualizer import get_visualizer
                    viz = get_visualizer()
            else:
                from .visualizer import get_visualizer
                viz = get_visualizer()
        except Exception:
            viz = None

        try:
            mode_name = mode_names.get(mode, "Recording")

            # Start latency tracking session
            tracker.start_session()

            # For Act on Text, use pre-captured selection
            selected_text = None
            if mode == ProcessingMode.ACT_ON_TEXT:
                selected_text = self._selected_text
                if not selected_text:
                    # This shouldn't happen - selection is checked before recording starts
                    print("⚠ No selection captured")
                    tracker.end_session()
                    return

            notify(f"🎤 {mode_name}", "Speak your instruction..." if mode == ProcessingMode.ACT_ON_TEXT else "Press FN to stop")

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
                result = self._process_text(
                    text, mode, selected_text, context=self._current_context
                )

            if result:
                # Stop visualizer before outputting text
                if viz:
                    viz.stop()
                    viz = None  # Don't stop again in finally

                with tracker.measure("text_output"):
                    self._output_result(
                        result, mode, selected_text is not None, context=self._current_context
                    )
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
            # Stop visualizer if not already stopped
            if viz:
                viz.stop()

    def _capture_selection_for_act_on_text(self) -> str | None:
        """Capture selected text for Act on Text mode (called before recording starts)"""
        try:
            from .platform_utils import IS_WAYLAND
            from .selection_handler import get_primary_selection, has_selection

            if not has_selection():
                print("⚠ No text selected")
                notify("⚠ No Selection", "Highlight text first, then press FN+Shift")
                return None

            selected = get_primary_selection()
            if not selected:
                tool_hint = "wl-clipboard" if IS_WAYLAND else "xclip"
                print(f"⚠ Could not read selection (install {tool_hint})")
                notify("⚠ Selection Error", f"Install {tool_hint}")
                return None

            return selected

        except ImportError as e:
            print(f"⚠ Selection handler not available: {e}")
            notify("⚠ Not Available", "Install xclip or wl-clipboard")
            return None

    def _process_text(
        self,
        text: str,
        mode: ProcessingMode,
        selected_text: str | None = None,
        context: ContextInfo | None = None,
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
                    return llm_processor.reformulate(text, context=context)
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
                print("⚠ LLM not available (set GEMINI_API_KEY or ANTHROPIC_API_KEY)")
                notify("⚠ LLM Not Available", "Configure LLM_PROVIDER")
                return text  # Fallback to raw text

            if mode == ProcessingMode.ACT_ON_TEXT and selected_text:
                return llm_processor.act_on_text(selected_text, text, context=context)

            elif mode == ProcessingMode.REFORMULATION:
                # Check if LLM reformulation is enabled
                if config.ENABLE_REFORMULATION:
                    return llm_processor.reformulate(text, context=context)
                else:
                    # Fallback to local filler removal only
                    return self._filter_fillers_local(text)

            elif mode == ProcessingMode.TRANSLATION:
                return llm_processor.translate(text, "English", context=context)

            elif mode == ProcessingMode.TRANSLATE_REFORMAT:
                # Translate first, then reformulate
                translated = llm_processor.translate(text, "English", context=context)
                if translated:
                    return llm_processor.reformulate(translated, context=context)
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

    def _output_result(
        self,
        text: str,
        mode: ProcessingMode,
        replace_selection: bool,
        context: ContextInfo | None = None,
    ):
        """Output the processed text using character-by-character typing.

        Args:
            text: The processed text to output.
            mode: The processing mode used.
            replace_selection: Whether we're replacing a selection (Act on Text).
            context: Optional context for adaptive typing speed.
        """
        # Calculate typing delay from context profile
        typing_delay_ms = 50  # Default: 50ms

        if context:
            from .context_profiles import get_profile_manager

            manager = get_profile_manager()
            profile = manager.match_context(context)
            if profile:
                # get_typing_delay returns seconds, convert to ms
                typing_delay_ms = int(manager.get_typing_delay(profile) * 1000)
                if config.CONTEXT_DEBUG:
                    print(f"[Context] Typing delay: {typing_delay_ms}ms ({profile.typing_speed})")

        # All modes use insert_text (xdotool type) for reliable output
        # For Act on Text: selection is still active, typing replaces it naturally
        self.keyboard.insert_text(text, typing_delay_ms=typing_delay_ms)

        if mode == ProcessingMode.ACT_ON_TEXT:
            print(f"✓ Replaced: {text[:50]}..." if len(text) > 50 else f"✓ {text}")
            notify("✓ Text Replaced", text[:100])
        else:
            print(f"✓ {text[:50]}..." if len(text) > 50 else f"✓ {text}")
            notify("✓ Done", text[:100])

    def _check_vpn_active(self) -> bool:
        """Check if a VPN is active (may block API calls)."""
        if IS_WINDOWS:
            return False  # TODO: Windows VPN detection

        try:
            import subprocess

            # Check for common VPN interfaces
            result = subprocess.run(
                ["ip", "link", "show"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            vpn_interfaces = ["tun", "tap", "wg", "vpn", "proton", "nord", "mullvad"]
            for iface in vpn_interfaces:
                if iface in result.stdout.lower():
                    return True
            return False
        except Exception:
            return False

    def run(self):
        """Run the application"""
        print("\n" + "=" * 50)
        print("🚀 Dicton")
        print("=" * 50)

        # Check for VPN that might block API calls
        if self._check_vpn_active():
            print("⚠ VPN detected - API calls may fail or timeout")
            print("  If dictation hangs, try disconnecting VPN")

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
            print("Modes: FN+Ctrl=Translate, FN+Shift=Act on Text (WIP)")
        else:
            print(f"Hotkey: {config.HOTKEY_MODIFIER}+{config.HOTKEY_KEY}")
            self.keyboard.start()

        print(f"STT: {self.recognizer.provider_name}")
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
  FN + Shift       Act on Text (WIP) - apply instruction to selection
  FN + Alt         LLM Reformulation (toggle: press to start/stop)
  FN + Space       Raw mode - no processing (toggle)

Examples:
  dicton                  Start dictation service
  dicton --config-ui      Open settings in browser
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
    parser.add_argument(
        "--config-ui",
        action="store_true",
        help="Launch configuration web UI in browser",
    )
    parser.add_argument(
        "--config-port",
        type=int,
        default=6873,
        help="Port for config UI server (default: 6873)",
    )

    args = parser.parse_args()

    if args.version:
        from . import __version__

        print(f"Dicton v{__version__}")
        return

    if args.config_ui:
        try:
            from .config_server import run_config_server

            run_config_server(port=args.config_port)
        except ImportError:
            print("Error: Configuration UI requires additional dependencies.")
            print("Install with: pip install dicton[configui]")
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
