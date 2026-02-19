"""Env configuration adapter producing a structured AppConfig."""

from __future__ import annotations

from ..config import config as legacy_config
from ..core.config_model import AppConfig


def load_app_config() -> AppConfig:
    return AppConfig(
        debug=legacy_config.DEBUG,
        notifications_enabled=legacy_config.NOTIFICATIONS_ENABLED,
        context_enabled=legacy_config.CONTEXT_ENABLED,
        context_debug=legacy_config.CONTEXT_DEBUG,
    )
