"""Null/console notification service for Dicton."""

from __future__ import annotations

from .notifications_base import NotificationService


class NullNotificationService(NotificationService):
    """Silent no-op — prints to console as fallback."""

    def notify(self, title: str, message: str, timeout: int = 2) -> None:
        print(f"[{title}] {message}")
