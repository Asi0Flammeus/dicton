"""Keyboard handler for Dicton - Cross-platform"""

import subprocess
import time

from .config import config
from .platform_utils import IS_LINUX, IS_MACOS, IS_WINDOWS


class KeyboardHandler:
    """Handle hotkey toggle and text insertion"""

    def __init__(self, on_toggle_callback):
        self.on_toggle = on_toggle_callback
        self.listener = None
        self.pressed_keys = set()
        self.hotkey_active = False
        self._keyboard_controller = None

    def _get_pynput_components(self):
        """Import pynput lazily so Linux startup can avoid X-only backends."""
        try:
            from pynput import keyboard as pynput_keyboard
            from pynput.keyboard import Controller as KeyboardController
            from pynput.keyboard import Key
        except Exception as exc:  # pragma: no cover - depends on local desktop backend
            raise ImportError(str(exc)) from exc

        return pynput_keyboard, KeyboardController, Key

    def _get_keyboard_controller(self):
        """Create the pynput controller only when a fallback path needs it."""
        if self._keyboard_controller is None:
            _, keyboard_controller_cls, _ = self._get_pynput_components()
            self._keyboard_controller = keyboard_controller_cls()
        return self._keyboard_controller

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

    def start(self):
        """Start keyboard listener"""
        pynput_keyboard, _, _ = self._get_pynput_components()
        self.listener = pynput_keyboard.Listener(
            on_press=self._on_press, on_release=self._on_release
        )
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
                    self._get_keyboard_controller().release(hotkey_char)
                except Exception:
                    pass
                if self.on_toggle:
                    self.on_toggle()
        except Exception:
            pass

    def _on_release(self, key):
        """Track key releases"""
        try:
            _, _, key_cls = self._get_pynput_components()

            if hasattr(key, "char") and key.char:
                self.pressed_keys.discard(key.char.lower())
            else:
                self.pressed_keys.discard(key)

            # Reset hotkey state when modifier released
            if key in (
                key_cls.alt,
                key_cls.alt_l,
                key_cls.alt_r,
                key_cls.ctrl,
                key_cls.ctrl_l,
                key_cls.ctrl_r,
            ):
                self.hotkey_active = False
        except Exception:
            pass

    def _is_hotkey_pressed(self) -> bool:
        """Check if configured hotkey is pressed"""
        _, _, key_cls = self._get_pynput_components()
        mod = config.HOTKEY_MODIFIER.lower()
        key = config.HOTKEY_KEY.lower()

        # Check modifier
        if mod in ("alt", "alt_l", "alt_r"):
            if not (
                key_cls.alt in self.pressed_keys
                or key_cls.alt_l in self.pressed_keys
                or key_cls.alt_r in self.pressed_keys
            ):
                return False
        elif mod in ("ctrl", "ctrl_l", "ctrl_r"):
            if not (
                key_cls.ctrl in self.pressed_keys
                or key_cls.ctrl_l in self.pressed_keys
                or key_cls.ctrl_r in self.pressed_keys
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

        The transcription stays in the clipboard after paste so the user
        can re-paste manually if the initial paste missed the target.
        """
        from .selection_handler import get_clipboard, set_clipboard

        try:
            if not set_clipboard(text):
                print("⚠ Failed to set clipboard, falling back to streaming")
                return False

            if not self._verify_clipboard(text, get_clipboard):
                print("⚠ Clipboard verification failed, falling back to streaming")
                return False

            subprocess.run(
                ["xdotool", "key", "--clearmodifiers", "ctrl+shift+v"],
                timeout=10,
                check=False,
            )

            return True

        except FileNotFoundError:
            print("⚠ xdotool not found for paste operation")
            return False
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
            keyboard_controller = self._get_keyboard_controller()
            for char in text:
                keyboard_controller.type(char)
                time.sleep(delay_seconds)
        except Exception as e:
            print(f"⚠ Text insertion error: {e}")

    def replace_selection_with_text(self, text: str) -> bool:
        """Replace the currently selected text with new text.

        Uses clipboard (Ctrl+V) method for reliable replacement across apps.
        The transcription stays in the clipboard for manual re-paste.

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
        """Replace selection on Linux using xclip + Ctrl+V.

        The transcription stays in the clipboard after paste so the user
        can re-paste manually if needed.
        """
        from .selection_handler import get_clipboard, set_clipboard

        try:
            if not set_clipboard(text):
                return False

            if not self._verify_clipboard(text, get_clipboard):
                print("⚠ Clipboard verification failed for selection replace")
                return False

            subprocess.run(
                ["xdotool", "key", "--clearmodifiers", "ctrl+v"],
                timeout=10,
                check=False,
            )

            return True

        except FileNotFoundError:
            print("⚠ xdotool not found for selection replace")
            return False
        except Exception as e:
            print(f"⚠ Replace selection error: {e}")
            return False

    def _replace_selection_windows(self, text: str) -> bool:
        """Replace selection on Windows using clipboard + Ctrl+V.

        The transcription stays in the clipboard after paste.
        """
        try:
            import pyperclip

            _, _, key_cls = self._get_pynput_components()
            keyboard_controller = self._get_keyboard_controller()

            pyperclip.copy(text)

            if not self._verify_clipboard(text, pyperclip.paste):
                print("⚠ Clipboard verification failed for Windows selection replace")
                return False

            keyboard_controller.press(key_cls.ctrl)
            keyboard_controller.press("v")
            keyboard_controller.release("v")
            keyboard_controller.release(key_cls.ctrl)

            return True

        except ImportError:
            print("⚠ pyperclip not installed for Windows clipboard")
            return False
        except Exception as e:
            print(f"⚠ Replace selection error: {e}")
            return False
