from __future__ import annotations

import shutil
import subprocess
import types

from dicton import visualizer


class _FakeScreen:
    def __init__(self) -> None:
        self.fills: list[tuple[int, int, int]] = []

    def fill(self, color: tuple[int, int, int]) -> None:
        self.fills.append(color)


class _FakeDisplay:
    def __init__(self) -> None:
        self.flips = 0

    def flip(self) -> None:
        self.flips += 1

    def get_wm_info(self) -> dict[str, int]:
        return {"window": 4242}


class _FakeWindow:
    def __init__(self) -> None:
        self.opacity = 1.0
        self.events: list[str] = []

    def hide(self) -> None:
        self.events.append("hide")

    def show(self) -> None:
        self.events.append("show")


def _fake_pygame(window: _FakeWindow, display: _FakeDisplay) -> object:
    class WindowFacade:
        @staticmethod
        def from_display_module() -> _FakeWindow:
            return window

    return types.SimpleNamespace(
        display=display,
        _sdl2=types.SimpleNamespace(video=types.SimpleNamespace(Window=WindowFacade)),
    )


def test_hidden_x11_visualizer_unmaps_window_without_touching_xshape() -> None:
    window = _FakeWindow()
    display = _FakeDisplay()
    pygame = _fake_pygame(window, display)
    screen = _FakeScreen()
    calls: list[bool] = []

    viz = visualizer.Visualizer()
    viz._xshape_ok = True
    viz._set_x11_bounding_shape = lambda _pygame, visible: calls.append(visible)  # type: ignore[attr-defined]

    viz._set_visible(pygame, screen, False)

    assert calls == []
    assert window.opacity == 0.0
    assert window.events == ["hide"]
    assert screen.fills == [(15, 15, 18)]
    assert display.flips == 1


def test_visible_x11_visualizer_remaps_window_and_restores_previous_focus(monkeypatch) -> None:
    window = _FakeWindow()
    display = _FakeDisplay()
    pygame = _fake_pygame(window, display)
    screen = _FakeScreen()
    calls: list[bool] = []
    commands: list[list[str]] = []

    def fake_run(cmd, **kwargs):  # noqa: ANN001, ANN202
        commands.append(cmd)
        if cmd == ["xdotool", "getactivewindow"]:
            return types.SimpleNamespace(stdout="9001\n")
        return types.SimpleNamespace(stdout="")

    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(subprocess, "run", fake_run)

    viz = visualizer.Visualizer()
    viz._xshape_ok = True
    viz._set_x11_bounding_shape = lambda _pygame, visible: calls.append(visible)  # type: ignore[attr-defined]

    viz._set_visible(pygame, screen, True)

    assert calls == []
    assert window.opacity == 0.85
    assert window.events == ["show"]
    assert commands == [
        ["xdotool", "getactivewindow"],
        ["xdotool", "windowactivate", "--sync", "9001"],
    ]
    assert screen.fills == []
    assert display.flips == 0
