"""Notification service ABC for Dicton."""

from __future__ import annotations

from abc import ABC, abstractmethod


class NotificationService(ABC):
    """Show desktop notifications."""

    @abstractmethod
    def notify(self, title: str, message: str, timeout: int = 2) -> None:
        """Display a notification. Should be silent on failure."""
