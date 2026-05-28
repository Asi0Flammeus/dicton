"""Paste tool selection: session-native first, with fallback."""

from __future__ import annotations

import os
from unittest import mock

# These tests pin Linux-specific behaviour: strategy ordering by session type
# (Wayland vs X11) and inter-strategy fallback. The public `paste()` dispatches
# on sys.platform and exposes none of that internal structure, so we drive the
# Linux backend directly.
from dicton.os_.paste import _linux as linux_backend


def _all_tools_present(cmd: str) -> str | None:
    return cmd if cmd in ("wl-copy", "xclip", "xdotool", "wtype") else None


def test_wayland_session_prefers_wl_copy() -> None:
    with (
        mock.patch.object(linux_backend.shutil, "which", _all_tools_present),
        mock.patch.dict(os.environ, {"WAYLAND_DISPLAY": "wayland-0"}),
    ):
        strategies = linux_backend._paste_strategies()
    assert strategies[0][0] == ["wl-copy"]


def test_x11_session_prefers_xclip() -> None:
    env = {k: v for k, v in os.environ.items() if k != "WAYLAND_DISPLAY"}
    with (
        mock.patch.object(linux_backend.shutil, "which", _all_tools_present),
        mock.patch.dict(os.environ, env, clear=True),
    ):
        strategies = linux_backend._paste_strategies()
    assert strategies[0][0] == ["xclip", "-selection", "clipboard"]


def test_paste_falls_back_when_first_copier_fails() -> None:
    """wl-copy exits non-zero (no Wayland socket) -> fall back to xclip."""
    calls: list[str] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd[0])
        if cmd[0] == "wl-copy":
            raise linux_backend.subprocess.CalledProcessError(1, cmd)
        return mock.Mock()

    with (
        mock.patch.object(linux_backend.shutil, "which", _all_tools_present),
        mock.patch.dict(os.environ, {"WAYLAND_DISPLAY": "wayland-0"}),
        mock.patch.object(linux_backend.subprocess, "run", side_effect=fake_run),
        mock.patch.object(linux_backend.time, "sleep"),
    ):
        linux_backend.paste_linux("hello")

    # Tried wl-copy first, fell back to xclip, then sent the keystroke.
    assert calls[0] == "wl-copy"
    assert "xclip" in calls
