"""Tests for Dicton hotkey parsing logic."""

from __future__ import annotations

import pytest

# Skip all tests if pynput is not available (CI environment without display)
pynput = pytest.importorskip("pynput", reason="pynput requires a display")
Key = pynput.keyboard.Key

from dicton.adapters.input.hotkey_listener import HotkeyListener  # noqa: E402
from dicton.shared.config import config  # noqa: E402


@pytest.fixture()
def _hotkey_env(monkeypatch):
    """Patch config attrs directly (class attrs are set at import time)."""

    def _set(modifier="alt", key="g"):
        monkeypatch.setattr(config, "HOTKEY_MODIFIER", modifier)
        monkeypatch.setattr(config, "HOTKEY_KEY", key)

    return _set


class TestHotkeyParsing:
    """Test hotkey configuration parsing."""

    def test_alt_modifier_recognized(self, _hotkey_env):
        _hotkey_env("alt", "g")
        handler = HotkeyListener(on_toggle_callback=lambda: None)
        handler.pressed_keys = {Key.alt, "g"}
        assert handler._is_hotkey_pressed() is True

    def test_ctrl_modifier_recognized(self, _hotkey_env):
        _hotkey_env("ctrl", "h")
        handler = HotkeyListener(on_toggle_callback=lambda: None)
        handler.pressed_keys = {Key.ctrl, "h"}
        assert handler._is_hotkey_pressed() is True

    def test_alt_l_variant(self, _hotkey_env):
        _hotkey_env("alt", "g")
        handler = HotkeyListener(on_toggle_callback=lambda: None)
        handler.pressed_keys = {Key.alt_l, "g"}
        assert handler._is_hotkey_pressed() is True

    def test_hotkey_not_pressed_without_modifier(self, _hotkey_env):
        _hotkey_env("alt", "g")
        handler = HotkeyListener(on_toggle_callback=lambda: None)
        handler.pressed_keys = {"g"}
        assert handler._is_hotkey_pressed() is False

    def test_hotkey_not_pressed_without_key(self, _hotkey_env):
        _hotkey_env("alt", "g")
        handler = HotkeyListener(on_toggle_callback=lambda: None)
        handler.pressed_keys = {Key.alt}
        assert handler._is_hotkey_pressed() is False

    def test_case_insensitive_key(self, _hotkey_env):
        _hotkey_env("alt", "G")
        handler = HotkeyListener(on_toggle_callback=lambda: None)
        handler.pressed_keys = {Key.alt, "g"}
        assert handler._is_hotkey_pressed() is True


class TestHotkeyListenerInit:
    """Test HotkeyListener initialization."""

    def test_init_with_callback(self):
        callback_called = []

        def callback():
            callback_called.append(True)

        handler = HotkeyListener(on_toggle_callback=callback)
        assert handler.on_toggle is callback
        assert handler.listener is None
        assert len(handler.pressed_keys) == 0

    def test_init_without_callback(self):
        handler = HotkeyListener(on_toggle_callback=None)
        assert handler.on_toggle is None
