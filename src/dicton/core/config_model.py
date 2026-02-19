"""Core configuration model (structured view)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AppConfig:
    debug: bool
    notifications_enabled: bool
    context_enabled: bool
    context_debug: bool
