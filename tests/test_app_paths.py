from __future__ import annotations

import importlib
from pathlib import PureWindowsPath


def test_linux_paths_default(monkeypatch):
    monkeypatch.delenv("DICTON_CONFIG_DIR", raising=False)
    monkeypatch.delenv("DICTON_DATA_DIR", raising=False)
    monkeypatch.delenv("DICTON_CACHE_DIR", raising=False)
    monkeypatch.setattr("sys.platform", "linux")

    import dicton.shared.app_paths as app_paths

    importlib.reload(app_paths)

    assert app_paths.get_user_config_dir().name == "dicton"
    assert ".config" in str(app_paths.get_user_config_dir())
    assert ".local" in str(app_paths.get_user_data_dir())
    assert ".cache" in str(app_paths.get_user_cache_dir())


def test_windows_paths_use_appdata(monkeypatch):
    monkeypatch.delenv("DICTON_CONFIG_DIR", raising=False)
    monkeypatch.delenv("DICTON_DATA_DIR", raising=False)
    monkeypatch.delenv("DICTON_CACHE_DIR", raising=False)
    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.setenv("APPDATA", r"C:\Users\Test\AppData\Roaming")
    monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\Test\AppData\Local")

    import dicton.shared.app_paths as app_paths

    importlib.reload(app_paths)

    assert PureWindowsPath(str(app_paths.get_user_config_dir())) == PureWindowsPath(
        r"C:\Users\Test\AppData\Roaming\dicton"
    )
    assert PureWindowsPath(str(app_paths.get_user_data_dir())) == PureWindowsPath(
        r"C:\Users\Test\AppData\Local\dicton"
    )
    assert PureWindowsPath(str(app_paths.get_user_cache_dir())) == PureWindowsPath(
        r"C:\Users\Test\AppData\Local\dicton\cache"
    )


def test_path_overrides_take_precedence(monkeypatch):
    monkeypatch.setenv("DICTON_CONFIG_DIR", "/tmp/dicton-config")
    monkeypatch.setenv("DICTON_DATA_DIR", "/tmp/dicton-data")
    monkeypatch.setenv("DICTON_CACHE_DIR", "/tmp/dicton-cache")

    import dicton.shared.app_paths as app_paths

    importlib.reload(app_paths)

    assert str(app_paths.get_user_config_dir()) == "/tmp/dicton-config"
    assert str(app_paths.get_user_data_dir()) == "/tmp/dicton-data"
    assert str(app_paths.get_user_cache_dir()) == "/tmp/dicton-cache"
