"""Factory for selecting the correct NotificationService by platform."""

from __future__ import annotations

from ...shared.config import Config
from ...shared.platform_utils import IS_LINUX, IS_MACOS, IS_WINDOWS
from .notifications_base import NotificationService
from .notifications_null import NullNotificationService


def get_notification_service() -> NotificationService:
    """Return the appropriate NotificationService for the current platform.

    Returns NullNotificationService if notifications are disabled in config.
    """
    if not Config.NOTIFICATIONS_ENABLED:
        return NullNotificationService()

    if IS_LINUX:
        from .notifications_linux import LinuxNotificationService

        return LinuxNotificationService()
    if IS_WINDOWS:
        from .notifications_windows import WindowsNotificationService

        return WindowsNotificationService()
    if IS_MACOS:
        from .notifications_macos import MacOSNotificationService

        return MacOSNotificationService()
    return NullNotificationService()
