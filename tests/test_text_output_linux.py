"""Unit tests for LinuxTextOutput with mocked subprocess."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

# Patch config where it's consumed, not where it's defined,
# to avoid stale-reference issues when test_config reloads the module.
_CONFIG_TARGET = "dicton.adapters.output.linux.config"


@pytest.fixture()
def selection_reader():
    reader = MagicMock()
    reader.set_clipboard.return_value = True

    # get_clipboard returns whatever set_clipboard last received
    def _get_clipboard():
        if reader.set_clipboard.call_args:
            return reader.set_clipboard.call_args[0][0]
        return None

    reader.get_clipboard.side_effect = _get_clipboard
    return reader


@pytest.fixture()
def output(selection_reader, monkeypatch):
    monkeypatch.setattr(_CONFIG_TARGET + ".PASTE_THRESHOLD_WORDS", 0)  # never paste by default
    from dicton.adapters.output.linux import LinuxTextOutput

    return LinuxTextOutput(selection_reader=selection_reader)


def test_insert_text_uses_xdotool(output):
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        output.insert_text("hello world", delay_ms=10)

    mock_run.assert_called_once()
    args = mock_run.call_args[0][0]
    assert args[0] == "xdotool"
    assert "hello world" in args


def test_insert_text_empty_string_is_noop(output):
    with patch("subprocess.run") as mock_run:
        output.insert_text("")
    mock_run.assert_not_called()


def test_insert_text_falls_back_on_file_not_found(output):
    with patch("subprocess.run", side_effect=FileNotFoundError()):
        with patch.object(output._pynput_fallback, "insert_text") as fallback:
            output.insert_text("hello")
    fallback.assert_called_once_with("hello", 50)


def test_paste_text_sets_clipboard_and_triggers_xdotool(output, selection_reader):
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        result = output.paste_text("hello world")

    assert result is True
    selection_reader.set_clipboard.assert_called_once_with("hello world")


def test_paste_text_returns_false_when_no_selection_reader(monkeypatch):
    from dicton.adapters.output.linux import LinuxTextOutput

    out = LinuxTextOutput(selection_reader=None)
    assert out.paste_text("text") is False


def test_paste_text_returns_false_when_set_clipboard_fails(output, selection_reader):
    selection_reader.set_clipboard.return_value = False
    result = output.paste_text("text")
    assert result is False


def test_replace_selection_uses_ctrl_v(output, selection_reader):
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        result = output.replace_selection("replaced")

    assert result is True
    # Last subprocess call should be xdotool key ctrl+v (not ctrl+shift+v)
    last_call_args = mock_run.call_args[0][0]
    assert "ctrl+v" in last_call_args


def test_paste_uses_ctrl_shift_v(output, selection_reader, monkeypatch):
    monkeypatch.setattr(_CONFIG_TARGET + ".PASTE_THRESHOLD_WORDS", 1)  # enable paste
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        output.insert_text("long text here", delay_ms=10)

    # Should call xdotool key ctrl+shift+v for paste path
    calls = [str(c) for c in mock_run.call_args_list]
    assert any("ctrl+shift+v" in c for c in calls)
