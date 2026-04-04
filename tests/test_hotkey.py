"""Tests for Dicton hotkey parsing logic."""

from __future__ import annotations

import pytest

# Skip all tests if pynput is not available (CI environment without display)
pynput = pytest.importorskip("pynput", reason="pynput requires a display")
Key = pynput.keyboard.Key

from dicton.adapters.input.hotkey_listener import HotkeyListener  # noqa: E402


def _make_listener(modifier="alt", key="g"):
    return HotkeyListener(
        on_toggle_callback=lambda: None,
        hotkey_modifier=modifier,
        hotkey_key=key,
    )


class TestHotkeyParsing:
    """Test hotkey configuration parsing."""

    def test_alt_modifier_recognized(self):
        handler = _make_listener("alt", "g")
        handler.pressed_keys = {Key.alt, "g"}
        assert handler._is_hotkey_pressed() is True

    def test_ctrl_modifier_recognized(self):
        handler = _make_listener("ctrl", "h")
        handler.pressed_keys = {Key.ctrl, "h"}
        assert handler._is_hotkey_pressed() is True

    def test_alt_l_variant(self):
        handler = _make_listener("alt", "g")
        handler.pressed_keys = {Key.alt_l, "g"}
        assert handler._is_hotkey_pressed() is True

    def test_hotkey_not_pressed_without_modifier(self):
        handler = _make_listener("alt", "g")
        handler.pressed_keys = {"g"}
        assert handler._is_hotkey_pressed() is False

    def test_hotkey_not_pressed_without_key(self):
        handler = _make_listener("alt", "g")
        handler.pressed_keys = {Key.alt}
        assert handler._is_hotkey_pressed() is False

    def test_case_insensitive_key(self):
        handler = _make_listener("alt", "G")
        handler.pressed_keys = {Key.alt, "g"}
        assert handler._is_hotkey_pressed() is True


class TestHotkeyListenerInit:
    """Test HotkeyListener initialization."""

    def test_init_with_callback(self):
        callback_called = []

        def callback():
            callback_called.append(True)

        handler = HotkeyListener(
            on_toggle_callback=callback,
            hotkey_modifier="alt",
            hotkey_key="g",
        )
        assert handler.on_toggle is callback
        assert handler.listener is None
        assert len(handler.pressed_keys) == 0

    def test_init_without_callback(self):
        handler = HotkeyListener(on_toggle_callback=None)
        assert handler.on_toggle is None
