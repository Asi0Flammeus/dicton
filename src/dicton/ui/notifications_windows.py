"""Windows notification service via plyer or win10toast."""

from __future__ import annotations

from .notifications_base import NotificationService


class WindowsNotificationService(NotificationService):
    """Notifications via plyer, fallback to win10toast."""

    def notify(self, title: str, message: str, timeout: int = 2) -> None:
        try:
            from plyer import notification

            notification.notify(title=title, message=message, timeout=timeout, app_name="Dicton")
        except ImportError:
            try:
                from win10toast import ToastNotifier

                toaster = ToastNotifier()
                toaster.show_toast(title, message, duration=timeout, threaded=True)
            except ImportError:
                print(f"[{title}] {message}")
        except Exception:
            pass
