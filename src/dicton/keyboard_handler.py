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

    def insert_text(self, text: str):
        """Insert text at cursor - cross-platform implementation"""
        if not text:
            return

        if IS_LINUX:
            self._insert_text_linux(text)
        elif IS_WINDOWS:
            self._insert_text_windows(text)
        elif IS_MACOS:
            self._insert_text_macos(text)
        else:
            self._insert_text_pynput(text)

    def _insert_text_linux(self, text: str):
        """Insert text on Linux - uses paste for long texts, streaming for short.

        For texts exceeding PASTE_THRESHOLD_WORDS, uses clipboard paste (instant).
        For shorter texts, uses xdotool streaming (typewriter effect).
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
            # 50ms delay (~200 words/min) prevents React Error #185 in React apps
            subprocess.run(["xdotool", "type", "--delay", "50", "--", text], timeout=60)
        except FileNotFoundError:
            # xdotool not installed, fallback to pynput
            print("⚠ xdotool not found, using fallback method")
            self._insert_text_pynput(text)
        except Exception as e:
            print(f"⚠ xdotool error: {e}, using fallback")
            self._insert_text_pynput(text)

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

            # Small delay to ensure clipboard is ready
            time.sleep(0.05)

            # Try Ctrl+Shift+V first (works in terminals + most GUI apps)
            self._keyboard_controller.press(Key.ctrl)
            self._keyboard_controller.press(Key.shift)
            self._keyboard_controller.press("v")
            self._keyboard_controller.release("v")
            self._keyboard_controller.release(Key.shift)
            self._keyboard_controller.release(Key.ctrl)

            # Small delay before restoring clipboard
            time.sleep(0.15)

            # Restore original clipboard if there was one
            if original_clipboard:
                set_clipboard(original_clipboard)

            return True

        except Exception as e:
            print(f"⚠ Paste error: {e}, falling back to streaming")
            return False

    def _insert_text_windows(self, text: str):
        """Insert text on Windows using pyautogui or pynput"""
        try:
            # Try pyautogui first (better Unicode support)
            import pyautogui

            # Disable fail-safe for text insertion
            pyautogui.FAILSAFE = False
            # 50ms delay (~200 words/min) prevents React Error #185 in React apps
            pyautogui.write(text, interval=0.05)
        except ImportError:
            # Fallback to pynput
            self._insert_text_pynput(text)
        except Exception as e:
            print(f"⚠ pyautogui error: {e}, using fallback")
            self._insert_text_pynput(text)

    def _insert_text_macos(self, text: str):
        """Insert text on macOS"""
        # pynput works well on macOS
        self._insert_text_pynput(text)

    def _insert_text_pynput(self, text: str):
        """Insert text using pynput keyboard controller (cross-platform fallback)"""
        try:
            # 50ms delay (~200 words/min) prevents React Error #185 in React apps
            for char in text:
                self._keyboard_controller.type(char)
                time.sleep(0.05)
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

            # Small delay to ensure clipboard is ready
            time.sleep(0.05)

            # Simulate Ctrl+V to paste
            self._keyboard_controller.press(Key.ctrl)
            self._keyboard_controller.press("v")
            self._keyboard_controller.release("v")
            self._keyboard_controller.release(Key.ctrl)

            # Small delay before restoring clipboard
            time.sleep(0.1)

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

            # Small delay
            time.sleep(0.05)

            # Simulate Ctrl+V
            self._keyboard_controller.press(Key.ctrl)
            self._keyboard_controller.press("v")
            self._keyboard_controller.release("v")
            self._keyboard_controller.release(Key.ctrl)

            # Restore original
            time.sleep(0.1)
            if original_clipboard:
                pyperclip.copy(original_clipboard)

            return True

        except ImportError:
            print("⚠ pyperclip not installed for Windows clipboard")
            return False
        except Exception as e:
            print(f"⚠ Replace selection error: {e}")
            return False
