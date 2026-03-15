"""macOS notification service via osascript."""

from __future__ import annotations

import subprocess

from .notifications_base import NotificationService


class MacOSNotificationService(NotificationService):
    """Notifications via osascript (AppleScript), fallback to plyer."""

    def notify(self, title: str, message: str, timeout: int = 2) -> None:
        try:
            script = f'display notification "{message}" with title "{title}"'
            subprocess.run(["osascript", "-e", script], timeout=2, capture_output=True)
        except Exception:
            self._notify_plyer(title, message, timeout)

    def _notify_plyer(self, title: str, message: str, timeout: int) -> None:
        try:
            from plyer import notification

            notification.notify(title=title, message=message, timeout=timeout, app_name="Dicton")
        except (ImportError, Exception):
            print(f"[{title}] {message}")
