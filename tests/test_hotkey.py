"""Tests for Dicton hotkey parsing logic."""

import importlib

import pytest

# Skip all tests if pynput is not available (CI environment without display)
pynput = pytest.importorskip("pynput", reason="pynput requires a display")
Key = pynput.keyboard.Key


def reload_modules():
    """Reload config and hotkey_listener to pick up env changes."""
    import dicton.config as config_module
    import dicton.input.hotkey_listener as hl_module

    importlib.reload(config_module)
    importlib.reload(hl_module)
    return hl_module


class TestHotkeyParsing:
    """Test hotkey configuration parsing."""

    def test_alt_modifier_recognized(self, clean_env, monkeypatch):
        """Test 'alt' modifier is recognized."""
        monkeypatch.setenv("HOTKEY_MODIFIER", "alt")
        monkeypatch.setenv("HOTKEY_KEY", "g")

        hl_module = reload_modules()
        handler = hl_module.HotkeyListener(on_toggle_callback=lambda: None)
        handler.pressed_keys = {Key.alt, "g"}

        assert handler._is_hotkey_pressed() is True

    def test_ctrl_modifier_recognized(self, clean_env, monkeypatch):
        """Test 'ctrl' modifier is recognized."""
        monkeypatch.setenv("HOTKEY_MODIFIER", "ctrl")
        monkeypatch.setenv("HOTKEY_KEY", "h")

        hl_module = reload_modules()
        handler = hl_module.HotkeyListener(on_toggle_callback=lambda: None)
        handler.pressed_keys = {Key.ctrl, "h"}

        assert handler._is_hotkey_pressed() is True

    def test_alt_l_variant(self, clean_env, monkeypatch):
        """Test left alt variant is recognized."""
        monkeypatch.setenv("HOTKEY_MODIFIER", "alt")
        monkeypatch.setenv("HOTKEY_KEY", "g")

        hl_module = reload_modules()
        handler = hl_module.HotkeyListener(on_toggle_callback=lambda: None)
        handler.pressed_keys = {Key.alt_l, "g"}

        assert handler._is_hotkey_pressed() is True

    def test_hotkey_not_pressed_without_modifier(self, clean_env, monkeypatch):
        """Test hotkey not triggered without modifier."""
        monkeypatch.setenv("HOTKEY_MODIFIER", "alt")
        monkeypatch.setenv("HOTKEY_KEY", "g")

        hl_module = reload_modules()
        handler = hl_module.HotkeyListener(on_toggle_callback=lambda: None)
        handler.pressed_keys = {"g"}  # Only key, no modifier

        assert handler._is_hotkey_pressed() is False

    def test_hotkey_not_pressed_without_key(self, clean_env, monkeypatch):
        """Test hotkey not triggered without the key."""
        monkeypatch.setenv("HOTKEY_MODIFIER", "alt")
        monkeypatch.setenv("HOTKEY_KEY", "g")

        hl_module = reload_modules()
        handler = hl_module.HotkeyListener(on_toggle_callback=lambda: None)
        handler.pressed_keys = {Key.alt}  # Only modifier, no key

        assert handler._is_hotkey_pressed() is False

    def test_case_insensitive_key(self, clean_env, monkeypatch):
        """Test key matching is case insensitive."""
        monkeypatch.setenv("HOTKEY_MODIFIER", "alt")
        monkeypatch.setenv("HOTKEY_KEY", "G")  # Uppercase

        hl_module = reload_modules()
        handler = hl_module.HotkeyListener(on_toggle_callback=lambda: None)
        handler.pressed_keys = {Key.alt, "g"}  # lowercase

        assert handler._is_hotkey_pressed() is True


class TestHotkeyListenerInit:
    """Test HotkeyListener initialization."""

    def test_init_with_callback(self):
        """Test listener initializes with callback."""
        hl_module = reload_modules()

        callback_called = []

        def callback():
            callback_called.append(True)

        handler = hl_module.HotkeyListener(on_toggle_callback=callback)
        assert handler.on_toggle is callback
        assert handler.listener is None
        assert len(handler.pressed_keys) == 0

    def test_init_without_callback(self):
        """Test listener initializes without callback."""
        hl_module = reload_modules()

        handler = hl_module.HotkeyListener(on_toggle_callback=None)
        assert handler.on_toggle is None
