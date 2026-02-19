"""UI feedback adapter."""

from __future__ import annotations

from ..ui_feedback import notify


class UIFeedbackAdapter:
    def notify(self, title: str, message: str) -> None:
        notify(title, message)
