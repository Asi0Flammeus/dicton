"""Pure state definitions for FN-key orchestration."""

from __future__ import annotations

from enum import Enum, auto


class HotkeyState(Enum):
    """State machine states for FN key detection.

    Double-tap toggle flow (BASIC mode):
        IDLE + key_down → TAP_DOWN
        TAP_DOWN + key_up → WAITING_DOUBLE (start double-tap timer)
        WAITING_DOUBLE + key_down (within window) → RECORDING_TOGGLE
        WAITING_DOUBLE + timeout → IDLE
        RECORDING_TOGGLE + key_down → IDLE (stop recording)

    Advanced / secondary hotkey flow:
        IDLE + key_down → RECORDING_TOGGLE (immediate)
        RECORDING_TOGGLE + key_down → IDLE (stop recording)
    """

    IDLE = auto()
    TAP_DOWN = auto()
    WAITING_DOUBLE = auto()
    RECORDING_TOGGLE = auto()
