"""UI theme constants for visualizer adapters.

Copied from ``shared.config`` so that adapters and the composition root can
reference them without importing the legacy singleton.
"""

from __future__ import annotations

from collections.abc import Callable

# Flexoki color palette - https://github.com/kepano/flexoki
FLEXOKI_COLORS: dict[str, dict[str, tuple[int, int, int]]] = {
    "red": {
        "main": (175, 48, 41),
        "mid": (140, 38, 33),
        "dim": (90, 25, 21),
        "glow": (209, 77, 65),
    },
    "orange": {
        "main": (188, 82, 21),
        "mid": (150, 65, 17),
        "dim": (95, 42, 11),
        "glow": (218, 112, 44),
    },
    "yellow": {
        "main": (173, 131, 1),
        "mid": (138, 105, 1),
        "dim": (87, 66, 1),
        "glow": (208, 162, 21),
    },
    "green": {
        "main": (102, 128, 11),
        "mid": (82, 102, 9),
        "dim": (51, 64, 6),
        "glow": (135, 154, 57),
    },
    "cyan": {
        "main": (36, 131, 123),
        "mid": (29, 105, 98),
        "dim": (18, 66, 62),
        "glow": (58, 169, 159),
    },
    "blue": {
        "main": (32, 94, 166),
        "mid": (26, 75, 133),
        "dim": (16, 47, 83),
        "glow": (67, 133, 190),
    },
    "purple": {
        "main": (94, 64, 157),
        "mid": (75, 51, 126),
        "dim": (47, 32, 79),
        "glow": (139, 126, 200),
    },
    "magenta": {
        "main": (160, 47, 111),
        "mid": (128, 38, 89),
        "dim": (80, 24, 56),
        "glow": (206, 93, 151),
    },
}

# Animation position options
POSITION_PRESETS: dict[str, Callable[[int, int, int], tuple[int, int]]] = {
    "top-right": lambda w, h, size: (w - size - 10, 0),
    "top-left": lambda w, h, size: (20, 10),
    "top-center": lambda w, h, size: ((w - size) // 2, 10),
    "bottom-right": lambda w, h, size: (w - size - 20, h - size - 60),
    "bottom-left": lambda w, h, size: (20, h - size - 60),
    "bottom-center": lambda w, h, size: ((w - size) // 2, h - size - 60),
    "center": lambda w, h, size: ((w - size) // 2, (h - size) // 2),
    "center-upper": lambda w, h, size: ((w - size) // 2, h // 3 - size // 2),
}


def get_theme_colors(
    color_name: str,
) -> dict[str, tuple[int, int, int]]:
    """Return the Flexoki sub-palette for *color_name*, falling back to orange."""
    if color_name not in FLEXOKI_COLORS:
        color_name = "orange"
    return FLEXOKI_COLORS[color_name]


def get_animation_position(
    position: str, screen_w: int, screen_h: int, size: int
) -> tuple[int, int]:
    """Return ``(x, y)`` for *position*, falling back to top-right."""
    if position not in POSITION_PRESETS:
        position = "top-right"
    fn = POSITION_PRESETS[position]
    return fn(screen_w, screen_h, size)
