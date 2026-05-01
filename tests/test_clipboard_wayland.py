"""Unit tests for WaylandClipboard with mocked wl-paste/wl-copy calls."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from dicton.adapters.output.clipboard_wayland import WaylandClipboard


@pytest.fixture()
def reader():
    return WaylandClipboard()


def _make_result(returncode: int = 0, stdout: str = "") -> MagicMock:
    r = MagicMock()
    r.returncode = returncode
    r.stdout = stdout
    return r


# ---------------------------------------------------------------------------
# get_clipboard
# ---------------------------------------------------------------------------


def test_get_clipboard_returns_text(reader):
    with patch("subprocess.run", return_value=_make_result(stdout="clipboard text")) as mock_run:
        result = reader.get_clipboard()

    assert result == "clipboard text"
    args = mock_run.call_args[0][0]
    assert "wl-paste" in args
    assert "-p" not in args


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
