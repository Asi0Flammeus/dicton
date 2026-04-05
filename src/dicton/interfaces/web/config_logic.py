"""Configuration logic, status checks, and dictionary operations."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

from ...shared.app_paths import get_user_config_dir
from ...shared.platform_utils import IS_LINUX, IS_MACOS, IS_WINDOWS, get_platform_info
from ...shared.startup import get_autostart_state, has_display_session
from .env_io import get_env_path, read_env_file, write_env_file

# ---------------------------------------------------------------------------
# Hardcoded defaults matching AppConfig / config_env defaults.  These are
# only used as fallbacks when a key is missing from both the .env file and
# os.environ.
# ---------------------------------------------------------------------------
_DEFAULTS: dict[str, str] = {
    "STT_PROVIDER": "auto",
    "LLM_PROVIDER": "gemini",
    "THEME_COLOR": "orange",
    "VISUALIZER_STYLE": "toric",
    "ANIMATION_POSITION": "top-right",
    "VISUALIZER_BACKEND": "pygame",
    "HOTKEY_BASE": "fn",
    "HOTKEY_DOUBLE_TAP_WINDOW_MS": "300",
    "LANGUAGE": "auto",
    "CUSTOM_HOTKEY_VALUE": "alt+g",
    "SECONDARY_HOTKEY": "none",
    "SECONDARY_HOTKEY_TRANSLATION": "none",
    "SECONDARY_HOTKEY_ACT_ON_TEXT": "none",
    "PLAYBACK_MUTE_STRATEGY": "auto",
    "MUTE_BACKEND": "auto",
}

CONFIG_FIELD_MAP = {
    "stt_provider": "STT_PROVIDER",
    "mistral_api_key": "MISTRAL_API_KEY",
    "elevenlabs_api_key": "ELEVENLABS_API_KEY",
    "gemini_api_key": "GEMINI_API_KEY",
    "anthropic_api_key": "ANTHROPIC_API_KEY",
    "llm_provider": "LLM_PROVIDER",
    "enable_advanced_modes": "ENABLE_ADVANCED_MODES",
    "theme_color": "THEME_COLOR",
    "visualizer_style": "VISUALIZER_STYLE",
    "animation_position": "ANIMATION_POSITION",
    "visualizer_backend": "VISUALIZER_BACKEND",
    "hotkey_base": "HOTKEY_BASE",
    "hotkey_double_tap_window_ms": "HOTKEY_DOUBLE_TAP_WINDOW_MS",
    "filter_fillers": "FILTER_FILLERS",
    "enable_reformulation": "ENABLE_REFORMULATION",
    "language": "LANGUAGE",
    "debug": "DEBUG",
    "custom_hotkey_value": "CUSTOM_HOTKEY_VALUE",
    "secondary_hotkey": "SECONDARY_HOTKEY",
    "secondary_hotkey_translation": "SECONDARY_HOTKEY_TRANSLATION",
    "secondary_hotkey_act_on_text": "SECONDARY_HOTKEY_ACT_ON_TEXT",
    "mute_playback_on_recording": "MUTE_PLAYBACK_ON_RECORDING",
    "playback_mute_strategy": "PLAYBACK_MUTE_STRATEGY",
    "mute_backend": "MUTE_BACKEND",
}

CONFIG_BOOL_FIELDS = {
    "enable_advanced_modes",
    "filter_fillers",
    "enable_reformulation",
    "debug",
    "mute_playback_on_recording",
}
CONFIG_STRING_FIELDS = set(CONFIG_FIELD_MAP) - CONFIG_BOOL_FIELDS

_setup_state: dict[str, Any] = {
    "first_test_passed": False,
    "last_test_text": "",
}


def _default(key: str) -> str:
    """Return the hardcoded default for *key*, falling back to ``""``."""
    return _DEFAULTS.get(key, "")


def _mask_api_key(key: str) -> str:
    """Mask API key showing first char + dots + last 2 chars."""
    if not key or len(key) < 4:
        return ""
    return f"{key[0]}{'•' * 8}{key[-2:]}"


def get_current_config() -> dict[str, Any]:
    """Get current configuration as dict."""
    env_vars = read_env_file()

    # Get API keys with masking
    mistral_key = env_vars.get("MISTRAL_API_KEY", "")
    elevenlabs_key = env_vars.get("ELEVENLABS_API_KEY", "")
    gemini_key = env_vars.get("GEMINI_API_KEY", "")
    anthropic_key = env_vars.get("ANTHROPIC_API_KEY", "")

    return {
        # STT settings
        "stt_provider": env_vars.get("STT_PROVIDER", _default("STT_PROVIDER")),
        # API keys - masked values for display
        "mistral_api_key_set": bool(mistral_key),
        "mistral_api_key_masked": _mask_api_key(mistral_key),
        "elevenlabs_api_key_set": bool(elevenlabs_key),
        "elevenlabs_api_key_masked": _mask_api_key(elevenlabs_key),
        "gemini_api_key_set": bool(gemini_key),
        "gemini_api_key_masked": _mask_api_key(gemini_key),
        "anthropic_api_key_set": bool(anthropic_key),
        "anthropic_api_key_masked": _mask_api_key(anthropic_key),
        # Other config values
        "llm_provider": env_vars.get("LLM_PROVIDER", _default("LLM_PROVIDER")),
        "enable_advanced_modes": (env_vars.get("ENABLE_ADVANCED_MODES", "false").lower() == "true"),
        "theme_color": env_vars.get("THEME_COLOR", _default("THEME_COLOR")),
        "visualizer_style": env_vars.get("VISUALIZER_STYLE", _default("VISUALIZER_STYLE")),
        "animation_position": env_vars.get("ANIMATION_POSITION", _default("ANIMATION_POSITION")),
        "visualizer_backend": env_vars.get("VISUALIZER_BACKEND", _default("VISUALIZER_BACKEND")),
        "hotkey_base": env_vars.get("HOTKEY_BASE", _default("HOTKEY_BASE")),
        "hotkey_double_tap_window_ms": env_vars.get(
            "HOTKEY_DOUBLE_TAP_WINDOW_MS", _default("HOTKEY_DOUBLE_TAP_WINDOW_MS")
        ),
        "filter_fillers": env_vars.get("FILTER_FILLERS", "true").lower() == "true",
        "enable_reformulation": env_vars.get("ENABLE_REFORMULATION", "false").lower() == "true",
        "language": env_vars.get("LANGUAGE", _default("LANGUAGE")),
        "debug": env_vars.get("DEBUG", "false").lower() == "true",
        # Hotkey settings
        "custom_hotkey_value": env_vars.get("CUSTOM_HOTKEY_VALUE", _default("CUSTOM_HOTKEY_VALUE")),
        "secondary_hotkey": env_vars.get("SECONDARY_HOTKEY", _default("SECONDARY_HOTKEY")),
        "secondary_hotkey_translation": env_vars.get(
            "SECONDARY_HOTKEY_TRANSLATION", _default("SECONDARY_HOTKEY_TRANSLATION")
        ),
        "secondary_hotkey_act_on_text": env_vars.get(
            "SECONDARY_HOTKEY_ACT_ON_TEXT", _default("SECONDARY_HOTKEY_ACT_ON_TEXT")
        ),
        "mute_playback_on_recording": (
            env_vars.get("MUTE_PLAYBACK_ON_RECORDING", "true").lower() == "true"
        ),
        "playback_mute_strategy": env_vars.get(
            "PLAYBACK_MUTE_STRATEGY", _default("PLAYBACK_MUTE_STRATEGY")
        ),
        "mute_backend": env_vars.get("MUTE_BACKEND", _default("MUTE_BACKEND")),
    }


def save_config(data: dict[str, Any]) -> None:
    """Save configuration to .env file."""
    env_vars = read_env_file()

    for ui_field, env_var in CONFIG_FIELD_MAP.items():
        if ui_field in data:
            value = data[ui_field]
            if isinstance(value, bool):
                value = "true" if value else "false"
            env_vars[env_var] = str(value)
            os.environ[env_var] = str(value)

    write_env_file(env_vars)

    # Refresh the legacy singleton so that any in-process code still using
    # ``shared.config.config`` sees the updated values.  We import locally
    # to keep the module-level dependency on ``shared.config`` removed.
    from ...shared.config import Config

    Config.reload_config()

    from ...adapters.stt.factory import clear_provider_cache

    clear_provider_cache()

    from ...adapters.llm.factory import cleanup as llm_cleanup

    llm_cleanup()


def _get_env_string(env_vars: dict[str, str], key: str, default: str = "") -> str:
    return env_vars.get(key, default).strip()


def _get_env_bool(env_vars: dict[str, str], key: str, default: bool = False) -> bool:
    if key not in env_vars:
        return default
    return env_vars[key].strip().lower() == "true"


def _stt_status(env_vars: dict[str, str]) -> dict[str, Any]:
    selected = _get_env_string(env_vars, "STT_PROVIDER", _default("STT_PROVIDER")).lower()
    has_mistral = bool(_get_env_string(env_vars, "MISTRAL_API_KEY"))
    has_elevenlabs = bool(_get_env_string(env_vars, "ELEVENLABS_API_KEY"))

    available = []
    if has_mistral:
        available.append("mistral")
    if has_elevenlabs:
        available.append("elevenlabs")

    if selected == "mistral":
        ready = has_mistral
        detail = "Mistral API key saved." if ready else "Add a Mistral API key."
    elif selected == "elevenlabs":
        ready = has_elevenlabs
        detail = "ElevenLabs API key saved." if ready else "Add an ElevenLabs API key."
    else:
        ready = bool(available)
        if ready:
            detail = f"Auto mode can use: {', '.join(name.title() for name in available)}."
        else:
            detail = "Add a Mistral or ElevenLabs API key."

    return {
        "ready": ready,
        "selected": selected,
        "available": available,
        "detail": detail,
    }


def _hotkey_status(env_vars: dict[str, str]) -> dict[str, Any]:
    hotkey_base = _get_env_string(env_vars, "HOTKEY_BASE", _default("HOTKEY_BASE")).lower()
    custom_hotkey = _get_env_string(
        env_vars, "CUSTOM_HOTKEY_VALUE", _default("CUSTOM_HOTKEY_VALUE")
    ).lower()

    if IS_LINUX:
        if hotkey_base in {"fn", "custom"}:
            try:
                import evdev  # noqa: F401
            except ImportError:
                return {
                    "ready": False,
                    "mode": hotkey_base,
                    "detail": "Linux FN/custom hotkeys require the evdev dependency.",
                }

            readable_devices = any(
                os.access(path, os.R_OK) for path in Path("/dev/input").glob("event*")
            )
            if not readable_devices:
                return {
                    "ready": False,
                    "mode": hotkey_base,
                    "detail": "Dicton cannot read /dev/input yet. Log out and back in after installation or add your user to the input group.",
                }

            if hotkey_base == "custom" and not custom_hotkey:
                return {
                    "ready": False,
                    "mode": hotkey_base,
                    "detail": "Choose a custom hotkey before continuing.",
                }

            return {
                "ready": True,
                "mode": hotkey_base,
                "detail": "Hotkey backend is ready.",
            }

        if os.environ.get("DISPLAY"):
            return {
                "ready": True,
                "mode": hotkey_base,
                "detail": "Legacy X11 hotkey backend is available.",
            }

        return {
            "ready": False,
            "mode": hotkey_base,
            "detail": "Legacy hotkeys require an X11 session. Prefer FN or custom mode on Linux.",
        }

    if hotkey_base == "custom" and not custom_hotkey:
        return {
            "ready": False,
            "mode": hotkey_base,
            "detail": "Choose a custom hotkey before continuing.",
        }

    return {
        "ready": True,
        "mode": hotkey_base,
        "detail": "Hotkey backend will use the packaged keyboard listener.",
    }


def _text_output_status() -> dict[str, Any]:
    if IS_LINUX:
        if shutil.which("xdotool"):
            return {
                "ready": True,
                "detail": "xdotool is installed for text insertion.",
            }
        return {
            "ready": False,
            "detail": "Install xdotool for reliable text insertion on Linux.",
        }

    if IS_WINDOWS:
        return {"ready": True, "detail": "Windows text insertion backend is available."}

    if IS_MACOS:
        return {
            "ready": True,
            "detail": "macOS text insertion backend uses the fallback keyboard driver.",
        }

    return {"ready": False, "detail": "Unsupported platform."}


def _llm_status(env_vars: dict[str, str]) -> dict[str, Any]:
    """Check whether an LLM provider key is configured for translation."""
    provider = env_vars.get("LLM_PROVIDER", _default("LLM_PROVIDER")).lower()
    gemini_key = env_vars.get("GEMINI_API_KEY", "")
    anthropic_key = env_vars.get("ANTHROPIC_API_KEY", "")

    if provider == "gemini" and gemini_key:
        return {"ready": True, "detail": "Gemini API key saved for translation."}
    if provider == "anthropic" and anthropic_key:
        return {"ready": True, "detail": "Anthropic API key saved for translation."}
    if gemini_key or anthropic_key:
        return {"ready": True, "detail": "LLM API key saved (translation available)."}

    return {
        "ready": False,
        "detail": "Set a Gemini or Anthropic API key to enable translation.",
    }


def build_setup_status() -> dict[str, Any]:
    """Build the setup/readiness status for the onboarding UI."""
    env_vars = read_env_file()
    stt = _stt_status(env_vars)
    hotkey = _hotkey_status(env_vars)
    output = _text_output_status()
    llm = _llm_status(env_vars)
    autostart = get_autostart_state()
    launch_ready = has_display_session()

    if not stt["ready"]:
        next_step = "speech"
    elif not hotkey["ready"]:
        next_step = "hotkey"
    elif autostart["supported"] and not autostart["enabled"]:
        next_step = "autostart"
    elif not _setup_state["first_test_passed"]:
        next_step = "test"
    else:
        next_step = "done"

    return {
        "platform": get_platform_info(),
        "config_path": str(get_env_path()),
        "config_saved": get_env_path().exists(),
        "first_test_passed": _setup_state["first_test_passed"],
        "last_test_text": _setup_state["last_test_text"],
        "launch_ready": launch_ready,
        "launch_detail": (
            "Desktop session detected." if launch_ready else "Start Dicton from a desktop session."
        ),
        "checks": {
            "stt": stt,
            "llm": llm,
            "hotkey": hotkey,
            "text_output": output,
            "autostart": autostart,
        },
        "next_step": next_step,
    }


def get_dictionary() -> dict[str, Any]:
    """Get dictionary contents."""
    dictionary_path = get_user_config_dir() / "dictionary.json"
    if not dictionary_path.exists():
        return {"similarity_words": [], "replacements": {}, "case_sensitive": {}, "patterns": []}

    try:
        with open(dictionary_path, encoding="utf-8") as f:
            data = json.load(f)
            # Ensure similarity_words exists
            if "similarity_words" not in data:
                data["similarity_words"] = []
            return data
    except (json.JSONDecodeError, OSError):
        return {"similarity_words": [], "replacements": {}, "case_sensitive": {}, "patterns": []}


def save_dictionary(data: dict[str, Any]) -> None:
    """Save dictionary to file."""
    dictionary_path = get_user_config_dir() / "dictionary.json"
    dictionary_path.parent.mkdir(parents=True, exist_ok=True)

    with open(dictionary_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def add_similarity_word(word: str) -> None:
    """Add a word to the similarity dictionary."""
    data = get_dictionary()
    if "similarity_words" not in data:
        data["similarity_words"] = []
    if word not in data["similarity_words"]:
        data["similarity_words"].append(word)
        save_dictionary(data)


def remove_similarity_word(word: str) -> None:
    """Remove a word from the similarity dictionary."""
    data = get_dictionary()
    if word in data.get("similarity_words", []):
        data["similarity_words"].remove(word)
        save_dictionary(data)
