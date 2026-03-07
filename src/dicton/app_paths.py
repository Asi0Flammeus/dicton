"""Cross-platform application paths for Dicton."""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "dicton"


def _home_fallback(*parts: str) -> Path:
    return Path.home().joinpath(*parts)


def get_user_config_dir() -> Path:
    """Return the per-user configuration directory."""
    override = os.getenv("DICTON_CONFIG_DIR")
    if override:
        return Path(override).expanduser()

    if sys.platform == "win32":
        return Path(os.getenv("APPDATA", _home_fallback("AppData", "Roaming"))) / APP_NAME
    if sys.platform == "darwin":
        return _home_fallback("Library", "Application Support", APP_NAME)
    return _home_fallback(".config", APP_NAME)


def get_user_data_dir() -> Path:
    """Return the per-user application data directory."""
    override = os.getenv("DICTON_DATA_DIR")
    if override:
        return Path(override).expanduser()

    if sys.platform == "win32":
        base = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA")
        return Path(base or _home_fallback("AppData", "Local")) / APP_NAME
    if sys.platform == "darwin":
        return _home_fallback("Library", "Application Support", APP_NAME)
    return _home_fallback(".local", "share", APP_NAME)


def get_user_cache_dir() -> Path:
    """Return the per-user cache directory."""
    override = os.getenv("DICTON_CACHE_DIR")
    if override:
        return Path(override).expanduser()

    if sys.platform == "win32":
        base = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA")
        return Path(base or _home_fallback("AppData", "Local")) / APP_NAME / "cache"
    if sys.platform == "darwin":
        return _home_fallback("Library", "Caches", APP_NAME)
    return _home_fallback(".cache", APP_NAME)


def get_user_env_path() -> Path:
    return get_user_config_dir() / ".env"


def get_user_contexts_path() -> Path:
    return get_user_config_dir() / "contexts.json"


def get_user_dictionary_path() -> Path:
    return get_user_config_dir() / "dictionary.json"


def get_latency_log_path() -> Path:
    return get_user_data_dir() / "latency.log"


def get_update_cache_path() -> Path:
    return get_user_cache_dir() / "update_cache.json"
