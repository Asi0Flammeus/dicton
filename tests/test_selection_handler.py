"""Tests for X11 and Wayland selection and clipboard handling."""

from types import SimpleNamespace

import dicton.selection_handler as selection_handler


def completed(stdout: str = "", returncode: int = 0):
    return SimpleNamespace(stdout=stdout, returncode=returncode)


def test_x11_selection_preserves_surrounding_whitespace(monkeypatch):
    expected = "  first line\nsecond line\n"
    monkeypatch.setattr(selection_handler, "IS_LINUX", True)
    monkeypatch.setattr(selection_handler, "IS_X11", True)
    monkeypatch.setattr(selection_handler, "IS_WAYLAND", False)
    monkeypatch.setattr(
        selection_handler.subprocess,
        "run",
        lambda *args, **kwargs: completed(expected),
    )

    assert selection_handler.get_primary_selection() == expected


def test_wayland_selection_falls_back_to_xwayland(monkeypatch):
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        if command[0] == "wl-paste":
            return completed(returncode=1)
        return completed("selected through XWayland")

    monkeypatch.setattr(selection_handler, "IS_LINUX", True)
    monkeypatch.setattr(selection_handler, "IS_X11", False)
    monkeypatch.setattr(selection_handler, "IS_WAYLAND", True)
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setattr(selection_handler.subprocess, "run", run)

    assert selection_handler.get_primary_selection() == "selected through XWayland"
    assert calls == [
        ["wl-paste", "-p", "-n"],
        ["xclip", "-selection", "primary", "-o"],
    ]


def test_wayland_clipboard_read_preserves_exact_text(monkeypatch):
    expected = "replacement\n"
    monkeypatch.setattr(selection_handler, "IS_LINUX", True)
    monkeypatch.setattr(selection_handler, "IS_WAYLAND", True)
    monkeypatch.setattr(
        selection_handler.subprocess,
        "run",
        lambda command, **kwargs: completed(expected),
    )

    assert selection_handler.get_clipboard() == expected


def test_wayland_clipboard_write_uses_wl_copy(monkeypatch):
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs.get("input")))
        return completed()

    monkeypatch.setattr(selection_handler, "IS_LINUX", True)
    monkeypatch.setattr(selection_handler, "IS_WAYLAND", True)
    monkeypatch.setattr(selection_handler.subprocess, "run", run)

    assert selection_handler.set_clipboard("transformed text") is True
    assert calls == [(["wl-copy"], "transformed text")]


def test_empty_selection_returns_none(monkeypatch):
    monkeypatch.setattr(selection_handler, "IS_LINUX", True)
    monkeypatch.setattr(selection_handler, "IS_X11", True)
    monkeypatch.setattr(selection_handler, "IS_WAYLAND", False)
    monkeypatch.setattr(
        selection_handler.subprocess,
        "run",
        lambda *args, **kwargs: completed(),
    )

    assert selection_handler.get_primary_selection() is None
    assert selection_handler.has_selection() is False
