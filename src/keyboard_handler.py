"""Keyboard handler for Push-to-Write"""
import subprocess
from pynput import keyboard
from pynput.keyboard import Key
from config import config


class KeyboardHandler:
    """Handle hotkey toggle and text insertion"""

    def __init__(self, on_toggle_callback):
        self.on_toggle = on_toggle_callback
        self.listener = None
        self.pressed_keys = set()
        self.hotkey_active = False

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

    @staticmethod
    def insert_text(text: str):
        """Insert text at cursor using xdotool"""
        if text:
            subprocess.run(['xdotool', 'type', '--', text], timeout=10)
