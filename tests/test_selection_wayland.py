"""Unit tests for WaylandSelectionReader with mocked wl-paste/wl-copy calls."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from dicton.adapters.output.selection_wayland import WaylandSelectionReader


@pytest.fixture()
def reader():
    return WaylandSelectionReader()


def _make_result(returncode: int = 0, stdout: str = "") -> MagicMock:
    r = MagicMock()
    r.returncode = returncode
    r.stdout = stdout
    return r


# ---------------------------------------------------------------------------
# get_selection (primary selection)
# ---------------------------------------------------------------------------


def test_get_selection_returns_text(reader):
    with patch("subprocess.run", return_value=_make_result(stdout="selected text")) as mock_run:
        result = reader.get_selection()

    assert result == "selected text"
    args = mock_run.call_args[0][0]
    assert "wl-paste" in args
    assert "-p" in args


def test_get_selection_returns_none_on_nonzero_returncode(reader):
    with patch("subprocess.run", return_value=_make_result(returncode=1)):
        result = reader.get_selection()
    assert result is None


def test_get_selection_returns_none_on_empty_stdout(reader):
    with patch("subprocess.run", return_value=_make_result(stdout="")):
        result = reader.get_selection()
    assert result is None


def test_get_selection_returns_none_when_wl_paste_missing(reader):
    with patch("subprocess.run", side_effect=FileNotFoundError()):
        result = reader.get_selection()
    assert result is None


def test_get_selection_returns_none_on_timeout(reader):
    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="wl-paste", timeout=2)):
        result = reader.get_selection()
    assert result is None


# ---------------------------------------------------------------------------
# get_clipboard
# ---------------------------------------------------------------------------


def test_get_clipboard_returns_text(reader):
    with patch("subprocess.run", return_value=_make_result(stdout="clipboard text")) as mock_run:
        result = reader.get_clipboard()

    assert result == "clipboard text"
    args = mock_run.call_args[0][0]
    assert "wl-paste" in args
    assert "-p" not in args  # no -p flag for clipboard (only primary uses -p)


def test_get_clipboard_returns_none_on_error(reader):
    with patch("subprocess.run", return_value=_make_result(returncode=1)):
        result = reader.get_clipboard()
    assert result is None


# ---------------------------------------------------------------------------
# set_clipboard
# ---------------------------------------------------------------------------


def test_set_clipboard_pipes_to_wl_copy(reader):
    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_process.communicate.return_value = ("", "")

    with patch("subprocess.Popen", return_value=mock_process) as mock_popen:
        result = reader.set_clipboard("some text")

    assert result is True
    args = mock_popen.call_args[0][0]
    assert "wl-copy" in args
    mock_process.communicate.assert_called_once_with(input="some text", timeout=2.0)


def test_set_clipboard_returns_false_for_empty_text(reader):
    result = reader.set_clipboard("")
    assert result is False


def test_set_clipboard_returns_false_on_file_not_found(reader):
    with patch("subprocess.Popen", side_effect=FileNotFoundError()):
        result = reader.set_clipboard("text")
    assert result is False


def test_set_clipboard_returns_false_on_nonzero_returncode(reader):
    mock_process = MagicMock()
    mock_process.returncode = 1
    mock_process.communicate.return_value = ("", "error")

    with patch("subprocess.Popen", return_value=mock_process):
        result = reader.set_clipboard("text")
    assert result is False
