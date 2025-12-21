#!/usr/bin/env python3
"""Dicton: Press Alt+T to record, press again to stop and transcribe"""

import os
import signal
import threading
import warnings

# Suppress warnings
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
warnings.filterwarnings("ignore")

from .config import config
from .keyboard_handler import KeyboardHandler
from .platform_utils import IS_WINDOWS
from .speech_recognition_engine import SpeechRecognizer
from .ui_feedback import notify


class Dicton:
    """Main application - simple toggle recording"""

    def __init__(self):
        config.create_dirs()
        self.recognizer = SpeechRecognizer()
        self.keyboard = KeyboardHandler(self.on_toggle)
        self.recording = False
        self.record_thread = None
        self._shutdown_event = threading.Event()

    def on_toggle(self):
        """Toggle recording on/off"""
        if self.recording:
            # Stop recording
            print("⏹ Stopping...")
            self.recognizer.stop()
            self.recording = False
        else:
            # Start recording
            self.recording = True
            self.record_thread = threading.Thread(target=self._record_and_transcribe, daemon=True)
            self.record_thread.start()

    def _record_and_transcribe(self):
        """Record audio and transcribe when done"""
        try:
            notify("🎤 Recording", "Press Alt+T to stop")

            # Record until stopped
            audio = self.recognizer.record()

            if audio is not None and len(audio) > 0:
                print("⏳ Transcribing...")
                text = self.recognizer.transcribe(audio)

                if text:
                    self.keyboard.insert_text(text)
                    print(f"✓ {text[:50]}..." if len(text) > 50 else f"✓ {text}")
                    notify("✓ Done", text[:100])
                else:
                    print("No speech detected")
                    notify("⚠ No speech", "Try again")
            else:
                print("No audio captured")

        except Exception as e:
            print(f"Error: {e}")
            notify("❌ Error", str(e)[:50])
        finally:
            self.recording = False

    def run(self):
        """Run the application"""
        print("\n" + "=" * 50)
        print("🚀 Dicton")
        print("=" * 50)
        print(f"Hotkey: {config.HOTKEY_MODIFIER}+{config.HOTKEY_KEY}")
        mode = "ElevenLabs realtime streaming" if self.recognizer.use_elevenlabs else "Local model"
        print(f"Mode: {mode}")
        print("\nPress hotkey to start/stop recording")
        print("Press Ctrl+C to quit")
        print("=" * 50 + "\n")

        self.keyboard.start()
        notify("Dicton Ready", f"Press {config.HOTKEY_MODIFIER}+{config.HOTKEY_KEY}")

        # Cross-platform wait loop
        try:
            if IS_WINDOWS:
                # Windows: use threading event wait
                self._shutdown_event.wait()
            else:
                # Unix: use signal.pause() for efficiency
                signal.pause()
        except KeyboardInterrupt:
            pass

        self.shutdown()

    def shutdown(self):
        """Clean shutdown"""
        print("\nShutting down...")
        self._shutdown_event.set()
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

    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    if not IS_WINDOWS:
        signal.signal(signal.SIGTERM, signal_handler)

    app.run()


if __name__ == "__main__":
    main()
