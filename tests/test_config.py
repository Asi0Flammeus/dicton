"""Config round-trip via tomllib."""

from __future__ import annotations

import tomllib
from pathlib import Path
from unittest import mock

from dicton import config


def test_round_trip(tmp_path: Path) -> None:
    custom_path = tmp_path / "config.toml"
    cfg = config.Config(
        groq_api_key="sk-foo",
        cleanup_model="openai/gpt-oss-120b",
        hotkey_primary="f3",
    )
    with (
        mock.patch.object(config, "CONFIG_PATH", custom_path),
        mock.patch.object(config, "CONFIG_DIR", custom_path.parent),
    ):
        cfg.save()
        loaded = tomllib.loads(custom_path.read_text())
    assert loaded["groq_api_key"] == "sk-foo"
    assert loaded["cleanup_model"] == "openai/gpt-oss-120b"
    assert loaded["hotkey_primary"] == "f3"
    assert loaded["chunk"]["min_chunk_s"] == 6.0


def test_load_returns_defaults_when_missing(tmp_path: Path) -> None:
    custom_path = tmp_path / "missing.toml"
    with mock.patch.object(config, "CONFIG_PATH", custom_path):
        cfg = config.load()
    assert cfg.groq_api_key == ""
    assert cfg.cleanup_model == "openai/gpt-oss-20b"


def test_fn_keycode_round_trip(tmp_path: Path) -> None:
    custom_path = tmp_path / "config.toml"
    cfg = config.Config(hotkey_primary="fn", hotkey_secondary="", hotkey_fn_keycode=190)
    with (
        mock.patch.object(config, "CONFIG_PATH", custom_path),
        mock.patch.object(config, "CONFIG_DIR", custom_path.parent),
    ):
        cfg.save()
        loaded = config.load()
    assert loaded.hotkey_fn_keycode == 190
    assert loaded.hotkey_secondary == ""


def test_fn_keycode_omitted_when_none(tmp_path: Path) -> None:
    custom_path = tmp_path / "config.toml"
    with (
        mock.patch.object(config, "CONFIG_PATH", custom_path),
        mock.patch.object(config, "CONFIG_DIR", custom_path.parent),
    ):
        config.Config().save()
        loaded = config.load()
    assert loaded.hotkey_fn_keycode is None
