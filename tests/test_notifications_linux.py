"""Unit tests for LinuxNotificationService with mocked notify-send."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from dicton.adapters.ui.notifications_linux import LinuxNotificationService


@pytest.fixture()
def service():
    return LinuxNotificationService()


def test_notify_calls_notify_send(service):
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        service.notify("Title", "Message", timeout=3)

    mock_run.assert_called_once()
    args = mock_run.call_args[0][0]
    assert args[0] == "notify-send"
    assert "Title" in args
    assert "Message" in args
    # timeout converted to milliseconds
    assert str(3 * 1000) in args


def test_notify_passes_correct_timeout(service):
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        service.notify("T", "M", timeout=5)

    args = mock_run.call_args[0][0]
    assert "5000" in args


def test_notify_falls_back_to_plyer_when_notify_send_missing(service, capsys):
    mock_notification = MagicMock()
    mock_plyer = MagicMock()
    mock_plyer.notification = mock_notification

    with patch("subprocess.run", side_effect=FileNotFoundError()):
        with patch.dict("sys.modules", {"plyer": mock_plyer}):
            service.notify("T", "M", timeout=2)

    mock_notification.notify.assert_called_once_with(
        title="T", message="M", timeout=2, app_name="Dicton"
    )


def test_notify_prints_when_both_fail(service, capsys):
    with patch("subprocess.run", side_effect=FileNotFoundError()):
        with patch.dict("sys.modules", {"plyer": None}):
            service.notify("Err", "Details", timeout=1)

    captured = capsys.readouterr()
    assert "Err" in captured.out
    assert "Details" in captured.out


def test_notify_silently_ignores_subprocess_exception(service):
    with patch(
        "subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="notify-send", timeout=2)
    ):
        # Should not raise
        service.notify("T", "M")


def test_notify_uses_default_timeout(service):
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        service.notify("T", "M")

    args = mock_run.call_args[0][0]
    # Default timeout is 2 → 2000 ms
    assert "2000" in args
