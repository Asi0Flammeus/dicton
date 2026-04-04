"""Windows text output via pyautogui + pyperclip."""

from __future__ import annotations

from .base import TextOutput
from .fallback import PynputTextOutput


class WindowsTextOutput(TextOutput):
    """Text output via pyautogui + pyperclip for Windows."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._pynput_fallback = PynputTextOutput()

    def insert_text(self, text: str, delay_ms: int = 50) -> None:
        if not text:
            return
        try:
            import pyautogui

            pyautogui.FAILSAFE = False
            pyautogui.write(text, interval=delay_ms / 1000.0)
        except ImportError:
            self._pynput_fallback.insert_text(text, delay_ms)
        except Exception as e:
            print(f"⚠ pyautogui error: {e}, using fallback")
            self._pynput_fallback.insert_text(text, delay_ms)

    def paste_text(self, text: str) -> bool:
        return self.replace_selection(text)

    def replace_selection(self, text: str) -> bool:
        try:
            import pyperclip

            _, _, key_cls = self._pynput_fallback._get_pynput_components()
            ctrl = self._pynput_fallback._get_keyboard_controller()

            pyperclip.copy(text)

            if not self._verify_clipboard(text, pyperclip.paste):
                print("⚠ Clipboard verification failed for Windows selection replace")
                return False

            ctrl.press(key_cls.ctrl)
            ctrl.press("v")
            ctrl.release("v")
            ctrl.release(key_cls.ctrl)
            return True

        except ImportError:
            print("⚠ pyperclip not installed for Windows clipboard")
            return False
        except Exception as e:
            print(f"⚠ Replace selection error: {e}")
            return False
