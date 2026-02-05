"""Keyboard handler for Dicton - Cross-platform"""

import subprocess
import time

from pynput import keyboard
from pynput.keyboard import Controller as KeyboardController
from pynput.keyboard import Key

from .config import config
from .platform_utils import IS_LINUX, IS_MACOS, IS_WINDOWS


class KeyboardHandler:
    """Handle hotkey toggle and text insertion"""

    def __init__(self, on_toggle_callback):
        self.on_toggle = on_toggle_callback
        self.listener = None
        self.pressed_keys = set()
        self.hotkey_active = False
        self._keyboard_controller = KeyboardController()

    def _verify_clipboard(self, expected_text: str, get_clipboard_fn) -> bool:
        """Verify clipboard contains expected text (prevents X11 race condition).

        X11 clipboard is asynchronous - xclip may exit before propagation.
        This method polls until clipboard matches or max retries exceeded.

        Comparison is whitespace-normalized because get_clipboard() strips
        the result while expected_text may contain trailing whitespace from
        LLM output.

        Args:
            expected_text: The text that should be in clipboard.
            get_clipboard_fn: Function to retrieve current clipboard content.

        Returns:
            True if clipboard contains expected text, False otherwise.
        """
        verify_delay = config.CLIPBOARD_VERIFY_DELAY_MS / 1000.0
        max_retries = config.CLIPBOARD_MAX_RETRIES
        expected_stripped = expected_text.strip()

        for attempt in range(max_retries):
            time.sleep(verify_delay)
            current = get_clipboard_fn()
            if current is not None and current.strip() == expected_stripped:
                return True
            if config.DEBUG:
                print(f"⚠ Clipboard verify attempt {attempt + 1}/{max_retries}: mismatch")

        return False

    @staticmethod
    def _compute_restore_delay(text_length: int) -> float:
        """Compute clipboard restore delay scaled to text length.

        The target app needs time to read the clipboard after receiving
        the paste keystroke.  Longer texts take more time to process
        (especially in Electron/web apps).

        Returns delay in seconds.
        """
        base = config.CLIPBOARD_RESTORE_DELAY_MS / 1000.0  # 0.25s default
        # Add 0.5ms per character beyond 100 chars
        extra = max(0, text_length - 100) * 0.0005
        # Cap at 5s to avoid excessively long waits
        return min(base + extra, 5.0)

    def start(self):
        """Start keyboard listener"""
        self.listener = keyboard.Listener(on_press=self._on_press, on_release=self._on_release)
        self.listener.start()

    def stop(self):
        """Stop keyboard listener"""
        if self.listener:
            self.listener.stop()

    def _on_press(self, key):
        """Track key presses and detect hotkey"""
        try:
            # Track the key
            if hasattr(key, "char") and key.char:
                self.pressed_keys.add(key.char.lower())
            else:
                self.pressed_keys.add(key)

            # Check hotkey and trigger once per press
            if self._is_hotkey_pressed() and not self.hotkey_active:
                self.hotkey_active = True
                # Release the hotkey character to prevent it from being typed
                # This "cancels" the pending keypress before apps receive it
                hotkey_char = config.HOTKEY_KEY.lower()
                try:
                    self._keyboard_controller.release(hotkey_char)
                except Exception:
                    pass
                if self.on_toggle:
                    self.on_toggle()
        except Exception:
            pass

    def _on_release(self, key):
        """Track key releases"""
        try:
            if hasattr(key, "char") and key.char:
                self.pressed_keys.discard(key.char.lower())
            else:
                self.pressed_keys.discard(key)

            # Reset hotkey state when modifier released
            if key in (Key.alt, Key.alt_l, Key.alt_r, Key.ctrl, Key.ctrl_l, Key.ctrl_r):
                self.hotkey_active = False
        except Exception:
            pass

    def _is_hotkey_pressed(self) -> bool:
        """Check if configured hotkey is pressed"""
        mod = config.HOTKEY_MODIFIER.lower()
        key = config.HOTKEY_KEY.lower()

        # Check modifier
        if mod in ("alt", "alt_l", "alt_r"):
            if not (
                Key.alt in self.pressed_keys
                or Key.alt_l in self.pressed_keys
                or Key.alt_r in self.pressed_keys
            ):
                return False
        elif mod in ("ctrl", "ctrl_l", "ctrl_r"):
            if not (
                Key.ctrl in self.pressed_keys
                or Key.ctrl_l in self.pressed_keys
                or Key.ctrl_r in self.pressed_keys
            ):
                return False

        return key in self.pressed_keys

    def insert_text(self, text: str, typing_delay_ms: int = 50):
        """Insert text at cursor - cross-platform implementation.

        Args:
            text: The text to insert.
            typing_delay_ms: Delay between keystrokes in milliseconds (default: 50ms).
                             Lower values = faster typing.
        """
        if not text:
            return

        if IS_LINUX:
            self._insert_text_linux(text, typing_delay_ms)
        elif IS_WINDOWS:
            self._insert_text_windows(text, typing_delay_ms)
        elif IS_MACOS:
            self._insert_text_macos(text, typing_delay_ms)
        else:
            self._insert_text_pynput(text, typing_delay_ms)

    def _insert_text_linux(self, text: str, typing_delay_ms: int = 50):
        """Insert text on Linux - uses paste for long texts, streaming for short.

        For texts exceeding PASTE_THRESHOLD_WORDS, uses clipboard paste (instant).
        For shorter texts, uses xdotool streaming (typewriter effect).

        Args:
            text: The text to insert.
            typing_delay_ms: Delay between keystrokes in milliseconds.
        """
        # Count words to determine method
        word_count = len(text.split())
        threshold = config.PASTE_THRESHOLD_WORDS

        # Use paste for long texts (threshold > 0 and exceeded) or always (-1)
        use_paste = threshold == -1 or (threshold > 0 and word_count > threshold)

        if use_paste:
            if config.DEBUG:
                print(f"📋 Using paste for {word_count} words (threshold: {threshold})")
            if self._paste_text_linux(text):
                return
            # Fallback to streaming if paste failed
            if config.DEBUG:
                print("⚠ Paste failed, falling back to streaming")

        # Use streaming (xdotool type) for short texts or as fallback
        try:
            # Use configured delay (default 50ms prevents React Error #185)
            subprocess.run(
                ["xdotool", "type", "--delay", str(typing_delay_ms), "--", text],
                timeout=60,
            )
        except FileNotFoundError:
            # xdotool not installed, fallback to pynput
            print("⚠ xdotool not found, using fallback method")
            self._insert_text_pynput(text, typing_delay_ms)
        except Exception as e:
            print(f"⚠ xdotool error: {e}, using fallback")
            self._insert_text_pynput(text, typing_delay_ms)

    def _paste_text_linux(self, text: str) -> bool:
        """Paste text on Linux using clipboard + Ctrl+Shift+V (terminal-compatible).

        Uses Ctrl+Shift+V for maximum compatibility:
        - Works in terminal apps (Claude Code, terminals)
        - Works in GUI apps (treated as paste or paste-without-formatting)

        Preserves original clipboard content.
        """
        from .selection_handler import get_clipboard, set_clipboard

        try:
            # Save current clipboard
            original_clipboard = get_clipboard()

            # Set new text to clipboard
            if not set_clipboard(text):
                print("⚠ Failed to set clipboard, falling back to streaming")
                return False

            # Verify clipboard was set correctly (prevents race condition)
            if not self._verify_clipboard(text, get_clipboard):
                print("⚠ Clipboard verification failed, falling back to streaming")
                if original_clipboard:
                    set_clipboard(original_clipboard)
                return False

            # Try Ctrl+Shift+V first (works in terminals + most GUI apps)
            self._keyboard_controller.press(Key.ctrl)
            self._keyboard_controller.press(Key.shift)
            self._keyboard_controller.press("v")
            self._keyboard_controller.release("v")
            self._keyboard_controller.release(Key.shift)
            self._keyboard_controller.release(Key.ctrl)

            # Delay before restoring clipboard to let the target app consume the paste.
            # Scale with text length: longer texts need more time for apps to process.
            restore_delay = self._compute_restore_delay(len(text))
            time.sleep(restore_delay)

            # Restore original clipboard if there was one
            if original_clipboard:
                set_clipboard(original_clipboard)

            return True

        except Exception as e:
            print(f"⚠ Paste error: {e}, falling back to streaming")
            return False

    def _insert_text_windows(self, text: str, typing_delay_ms: int = 50):
        """Insert text on Windows using pyautogui or pynput.

        Args:
            text: The text to insert.
            typing_delay_ms: Delay between keystrokes in milliseconds.
        """
        try:
            # Try pyautogui first (better Unicode support)
            import pyautogui

            # Disable fail-safe for text insertion
            pyautogui.FAILSAFE = False
            # Convert ms to seconds for pyautogui
            pyautogui.write(text, interval=typing_delay_ms / 1000.0)
        except ImportError:
            # Fallback to pynput
            self._insert_text_pynput(text, typing_delay_ms)
        except Exception as e:
            print(f"⚠ pyautogui error: {e}, using fallback")
            self._insert_text_pynput(text, typing_delay_ms)

    def _insert_text_macos(self, text: str, typing_delay_ms: int = 50):
        """Insert text on macOS.

        Args:
            text: The text to insert.
            typing_delay_ms: Delay between keystrokes in milliseconds.
        """
        # pynput works well on macOS
        self._insert_text_pynput(text, typing_delay_ms)

    def _insert_text_pynput(self, text: str, typing_delay_ms: int = 50):
        """Insert text using pynput keyboard controller (cross-platform fallback).

        Args:
            text: The text to insert.
            typing_delay_ms: Delay between keystrokes in milliseconds.
        """
        try:
            # Convert ms to seconds for sleep
            delay_seconds = typing_delay_ms / 1000.0
            for char in text:
                self._keyboard_controller.type(char)
                time.sleep(delay_seconds)
        except Exception as e:
            print(f"⚠ Text insertion error: {e}")

    def replace_selection_with_text(self, text: str) -> bool:
        """Replace the currently selected text with new text.

        Uses clipboard (Ctrl+V) method for reliable replacement across apps.
        Preserves original clipboard content.

        Args:
            text: The text to replace selection with.

        Returns:
            True if successful, False otherwise.
        """
        if not text:
            return False

        if IS_LINUX:
            return self._replace_selection_linux(text)
        elif IS_WINDOWS:
            return self._replace_selection_windows(text)
        else:
            return False

    def _replace_selection_linux(self, text: str) -> bool:
        """Replace selection on Linux using xclip + Ctrl+V"""
        from .selection_handler import get_clipboard, set_clipboard

        try:
            # Save current clipboard
            original_clipboard = get_clipboard()

            # Set new text to clipboard
            if not set_clipboard(text):
                return False

            # Verify clipboard was set correctly (prevents race condition)
            if not self._verify_clipboard(text, get_clipboard):
                print("⚠ Clipboard verification failed for selection replace")
                if original_clipboard:
                    set_clipboard(original_clipboard)
                return False

            # Simulate Ctrl+V to paste
            self._keyboard_controller.press(Key.ctrl)
            self._keyboard_controller.press("v")
            self._keyboard_controller.release("v")
            self._keyboard_controller.release(Key.ctrl)

            # Scale delay with text length (same logic as paste)
            restore_delay = self._compute_restore_delay(len(text))
            time.sleep(restore_delay)

            # Restore original clipboard if there was one
            if original_clipboard:
                set_clipboard(original_clipboard)

            return True

        except Exception as e:
            print(f"⚠ Replace selection error: {e}")
            return False

    def _replace_selection_windows(self, text: str) -> bool:
        """Replace selection on Windows using clipboard + Ctrl+V"""
        try:
            import pyperclip

            # Save current clipboard
            try:
                original_clipboard = pyperclip.paste()
            except Exception:
                original_clipboard = None

            # Set new text
            pyperclip.copy(text)

            # Verify clipboard was set correctly (Windows clipboard can also be async)
            if not self._verify_clipboard(text, pyperclip.paste):
                print("⚠ Clipboard verification failed for Windows selection replace")
                if original_clipboard:
                    pyperclip.copy(original_clipboard)
                return False

            # Simulate Ctrl+V
            self._keyboard_controller.press(Key.ctrl)
            self._keyboard_controller.press("v")
            self._keyboard_controller.release("v")
            self._keyboard_controller.release(Key.ctrl)

            # Scale delay with text length
            restore_delay = self._compute_restore_delay(len(text))
            time.sleep(restore_delay)

            # Restore original clipboard
            if original_clipboard:
                pyperclip.copy(original_clipboard)

            return True

        except ImportError:
            print("⚠ pyperclip not installed for Windows clipboard")
            return False
        except Exception as e:
            print(f"⚠ Replace selection error: {e}")
            return False
