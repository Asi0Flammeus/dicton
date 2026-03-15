"""Pure state definitions for FN-key orchestration."""

from __future__ import annotations

from enum import Enum, auto


class HotkeyState(Enum):
    """State machine states for FN key detection."""

    IDLE = auto()
    WAITING_ACTIVATION = auto()
    RECORDING_PTT = auto()
    WAITING_DOUBLE = auto()
    RECORDING_TOGGLE = auto()
