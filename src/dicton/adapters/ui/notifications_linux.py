"""Linux notification service via notify-send."""

from __future__ import annotations

import subprocess

from .notifications_base import NotificationService


class LinuxNotificationService(NotificationService):
    """Notifications via notify-send (D-Bus), fallback to plyer."""

    def notify(self, title: str, message: str, timeout: int = 2) -> None:
        try:
            subprocess.run(
                ["notify-send", "-t", str(timeout * 1000), title, message],
                timeout=2,
                capture_output=True,
            )
        except FileNotFoundError:
            self._notify_plyer(title, message, timeout)
        except Exception:
            pass

    def _notify_plyer(self, title: str, message: str, timeout: int) -> None:
        try:
            from plyer import notification

            notification.notify(title=title, message=message, timeout=timeout, app_name="Dicton")
        except ImportError:
            print(f"[{title}] {message}")
        except Exception:
            print(f"[{title}] {message}")
