"""Simple session state machine for dictation flow."""

from __future__ import annotations

from enum import Enum, auto
import logging


class SessionState(Enum):
    IDLE = auto()
    RECORDING = auto()
    PROCESSING = auto()
    OUTPUTTING = auto()
    ERROR = auto()


class SessionEvent(Enum):
    START = auto()
    STOP = auto()
    CANCEL = auto()
    PROCESS_DONE = auto()
    OUTPUT_DONE = auto()
    ERROR = auto()
    RESET = auto()


_TRANSITIONS = {
    SessionState.IDLE: {
        SessionEvent.START: SessionState.RECORDING,
    },
    SessionState.RECORDING: {
        SessionEvent.STOP: SessionState.PROCESSING,
        SessionEvent.CANCEL: SessionState.IDLE,
        SessionEvent.ERROR: SessionState.ERROR,
    },
    SessionState.PROCESSING: {
        SessionEvent.PROCESS_DONE: SessionState.OUTPUTTING,
        SessionEvent.ERROR: SessionState.ERROR,
    },
    SessionState.OUTPUTTING: {
        SessionEvent.OUTPUT_DONE: SessionState.IDLE,
        SessionEvent.ERROR: SessionState.ERROR,
    },
    SessionState.ERROR: {
        SessionEvent.RESET: SessionState.IDLE,
    },
}


class SessionStateMachine:
    def __init__(self):
        self.state = SessionState.IDLE

    def transition(self, event: SessionEvent) -> SessionState:
        next_state = _TRANSITIONS.get(self.state, {}).get(event, self.state)
        if next_state == self.state and event not in _TRANSITIONS.get(self.state, {}):
            logging.getLogger(__name__).warning(
                "Invalid state transition: %s --%s--> %s", self.state, event, next_state
            )
        self.state = next_state
        return self.state
