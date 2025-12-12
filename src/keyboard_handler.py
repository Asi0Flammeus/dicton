"""Keyboard handler for Push-to-Write - Cross-platform"""
import subprocess
import time
from pynput import keyboard
from pynput.keyboard import Key, Controller as KeyboardController
from config import config
from platform_utils import IS_WINDOWS, IS_LINUX, IS_MACOS


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
        self.listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release
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
            if hasattr(key, 'char') and key.char:
                self.pressed_keys.add(key.char.lower())
            else:
                self.pressed_keys.add(key)

            # Check hotkey and trigger once per press
            if self._is_hotkey_pressed() and not self.hotkey_active:
                self.hotkey_active = True
                if self.on_toggle:
                    self.on_toggle()
        except Exception:
            pass

    def _on_release(self, key):
        """Track key releases"""
        try:
            if hasattr(key, 'char') and key.char:
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
            if not (Key.alt in self.pressed_keys or
                    Key.alt_l in self.pressed_keys or
                    Key.alt_r in self.pressed_keys):
                return False
        elif mod in ("ctrl", "ctrl_l", "ctrl_r"):
            if not (Key.ctrl in self.pressed_keys or
                    Key.ctrl_l in self.pressed_keys or
                    Key.ctrl_r in self.pressed_keys):
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
            # Fallback: use pynput (slower but universal)
            self._insert_text_pynput(text)

    def _insert_text_linux(self, text: str):
        """Insert text on Linux using xdotool"""
        try:
            subprocess.run(['xdotool', 'type', '--', text], timeout=10)
        except FileNotFoundError:
            # xdotool not installed, fallback to pynput
            print("⚠ xdotool not found, using fallback method")
            self._insert_text_pynput(text)
        except Exception as e:
            print(f"⚠ xdotool error: {e}, using fallback")
            self._insert_text_pynput(text)

    def _insert_text_windows(self, text: str):
        """Insert text on Windows using pyautogui or pynput"""
        try:
            # Try pyautogui first (better Unicode support)
            import pyautogui
            # Disable fail-safe for text insertion
            pyautogui.FAILSAFE = False
            pyautogui.write(text, interval=0.01)
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
            # Type character by character with small delay
            for char in text:
                self._keyboard_controller.type(char)
                time.sleep(0.005)  # Small delay for reliability
        except Exception as e:
            print(f"⚠ Text insertion error: {e}")
