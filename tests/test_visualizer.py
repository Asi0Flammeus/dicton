from __future__ import annotations

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


class _FakeWindow:
    def __init__(self) -> None:
        self.opacity = 1.0


def _fake_pygame(window: _FakeWindow, display: _FakeDisplay) -> object:
    class WindowFacade:
        @staticmethod
        def from_display_module() -> _FakeWindow:
            return window

    return types.SimpleNamespace(
        display=display,
        _sdl2=types.SimpleNamespace(video=types.SimpleNamespace(Window=WindowFacade)),
    )


def test_hidden_x11_visualizer_does_not_touch_xshape_after_startup() -> None:
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
    assert screen.fills == [(15, 15, 18)]
    assert display.flips == 1


def test_visible_x11_visualizer_uses_sdl_opacity_only() -> None:
    window = _FakeWindow()
    display = _FakeDisplay()
    pygame = _fake_pygame(window, display)
    screen = _FakeScreen()
    calls: list[bool] = []

    viz = visualizer.Visualizer()
    viz._xshape_ok = True
    viz._set_x11_bounding_shape = lambda _pygame, visible: calls.append(visible)  # type: ignore[attr-defined]

    viz._set_visible(pygame, screen, True)

    assert calls == []
    assert window.opacity == 0.85
    assert screen.fills == []
    assert display.flips == 0
