"""Unit tests for WindowsTextOutput with mocked pyautogui/pyperclip."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _mock_pyautogui():
    mock = MagicMock()
    mock.FAILSAFE = True
    sys.modules["pyautogui"] = mock
    yield mock
    sys.modules.pop("pyautogui", None)


@pytest.fixture(autouse=True)
def _mock_pyperclip():
    mock = MagicMock()
    mock.paste.return_value = "copied text"
    sys.modules["pyperclip"] = mock
    yield mock
    sys.modules.pop("pyperclip", None)


@pytest.fixture()
def output():
    from dicton.adapters.output.windows import WindowsTextOutput

    return WindowsTextOutput()


def test_insert_text_calls_pyautogui_write(output, _mock_pyautogui):
    output.insert_text("hello", delay_ms=20)
    _mock_pyautogui.write.assert_called_once_with("hello", interval=0.02)


def test_insert_text_empty_is_noop(output, _mock_pyautogui):
    output.insert_text("")
    _mock_pyautogui.write.assert_not_called()


def test_insert_text_falls_back_when_pyautogui_missing(output):
    sys.modules.pop("pyautogui", None)
    with patch.object(output._pynput_fallback, "insert_text") as fallback:
        output.insert_text("hello")
    fallback.assert_called_once()


def test_paste_text_copies_to_clipboard_and_pastes(output, _mock_pyperclip):
    mock_key_cls = MagicMock()
    mock_ctrl = MagicMock()
    with patch.object(
        output._pynput_fallback,
        "_get_pynput_components",
        return_value=(MagicMock(), MagicMock(), mock_key_cls),
    ):
        with patch.object(
            output._pynput_fallback,
            "_get_keyboard_controller",
            return_value=mock_ctrl,
        ):
            with patch.object(output, "_verify_clipboard", return_value=True):
                result = output.paste_text("pasted")

    assert result is True
    _mock_pyperclip.copy.assert_called_once_with("pasted")


def test_paste_text_returns_false_when_clipboard_verify_fails(output, _mock_pyperclip):
    mock_key_cls = MagicMock()
    mock_ctrl = MagicMock()
    with patch.object(
        output._pynput_fallback,
        "_get_pynput_components",
        return_value=(MagicMock(), MagicMock(), mock_key_cls),
    ):
        with patch.object(
            output._pynput_fallback,
            "_get_keyboard_controller",
            return_value=mock_ctrl,
        ):
            with patch.object(output, "_verify_clipboard", return_value=False):
                result = output.paste_text("pasted")

    assert result is False
