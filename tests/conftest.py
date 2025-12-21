"""Pytest fixtures for Dicton tests."""

import pytest


@pytest.fixture
def temp_env(tmp_path, monkeypatch):
    """Create a temporary .env file and set environment for testing."""
    env_file = tmp_path / ".env"

    def _create_env(content: str = ""):
        env_file.write_text(content)
        monkeypatch.chdir(tmp_path)
        return env_file

    return _create_env


@pytest.fixture
def clean_env(monkeypatch):
    """Clear all Dicton-related environment variables."""
    env_vars = [
        "ELEVENLABS_API_KEY",
        "ELEVENLABS_MODEL",
        "HOTKEY_MODIFIER",
        "HOTKEY_KEY",
        "THEME_COLOR",
        "ANIMATION_POSITION",
        "VISUALIZER_STYLE",
        "VISUALIZER_BACKEND",
        "MIC_DEVICE",
        "LANGUAGE",
        "DEBUG",
    ]
    for var in env_vars:
        monkeypatch.delenv(var, raising=False)
    return env_vars


@pytest.fixture
def mock_platform(monkeypatch):
    """Mock platform detection values."""

    def _mock(system: str = "linux", session_type: str = "x11"):
        if system == "linux":
            monkeypatch.setattr("sys.platform", "linux")
            monkeypatch.setenv("XDG_SESSION_TYPE", session_type)
            if session_type == "x11":
                monkeypatch.setenv("DISPLAY", ":0")
            else:
                monkeypatch.delenv("DISPLAY", raising=False)
        elif system == "windows":
            monkeypatch.setattr("sys.platform", "win32")
        elif system == "macos":
            monkeypatch.setattr("sys.platform", "darwin")
        return system

    return _mock
