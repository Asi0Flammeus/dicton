"""Keyboard hotkey listener for Dicton."""

from ..config import config


class HotkeyListener:
    """Listen for configured hotkey and trigger on_toggle callback."""

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

    def start(self):
        """Start keyboard listener."""
        pynput_keyboard, _, _ = self._get_pynput_components()
        self.listener = pynput_keyboard.Listener(
            on_press=self._on_press, on_release=self._on_release
        )
        self.listener.start()

    def stop(self):
        """Stop keyboard listener."""
        if self.listener:
            self.listener.stop()

    def _on_press(self, key):
        """Track key presses and detect hotkey."""
        try:
            if hasattr(key, "char") and key.char:
                self.pressed_keys.add(key.char.lower())
            else:
                self.pressed_keys.add(key)

            if self._is_hotkey_pressed() and not self.hotkey_active:
                self.hotkey_active = True
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
        """Track key releases."""
        try:
            _, _, key_cls = self._get_pynput_components()

            if hasattr(key, "char") and key.char:
                self.pressed_keys.discard(key.char.lower())
            else:
                self.pressed_keys.discard(key)

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
        """Check if configured hotkey is pressed."""
        _, _, key_cls = self._get_pynput_components()
        mod = config.HOTKEY_MODIFIER.lower()
        key = config.HOTKEY_KEY.lower()

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
