"""Configuration dataclass for visualizer adapters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable


@dataclass(frozen=True)
class VisualizerConfig:
    """Resolved configuration values for visualizer adapters.

    Constructed in the composition root and injected into visualizer
    constructors so they never import ``shared.config`` directly.
    """

    # Resolved theme palette – ``{'main': (r,g,b), 'mid': …, 'dim': …, 'glow': …}``
    theme_colors: dict[str, tuple[int, int, int]]

    # Full Flexoki palette keyed by colour name, for ``set_colors()``
    flexoki_colors: dict[str, dict[str, tuple[int, int, int]]]

    # Divisor for raw-RMS → 0-1 normalisation
    rms_normalization: int

    # ``(screen_w, screen_h, size) -> (x, y)``
    animation_position_fn: Callable[[int, int, int], tuple[int, int]]

    debug: bool

    # Pygame-specific: window opacity on Linux (0.0–1.0)
    opacity: float = 0.85

    # VisPy-specific: visualizer style name
    visualizer_style: str = "toric"
