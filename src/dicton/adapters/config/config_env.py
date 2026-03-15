"""Env configuration adapter producing a structured AppConfig."""

from __future__ import annotations

from ...core.config_model import AppConfig
from ...shared.config import config as legacy_config


def load_app_config() -> AppConfig:
    return AppConfig(
        debug=legacy_config.DEBUG,
        notifications_enabled=legacy_config.NOTIFICATIONS_ENABLED,
    )
