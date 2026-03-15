"""System tray ABC for Dicton."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ...core.state_machine import SessionState

# Flexoki-derived icon colors per state
_STATE_COLORS: dict[str, str] = {
    "IDLE": "#100F0F",
    "RECORDING": "#BC5215",
    "PROCESSING": "#205EA6",
    "OUTPUTTING": "#205EA6",
    "ERROR": "#AF3029",
}

_STATE_LABELS: dict[str, str] = {
    "IDLE": "Idle",
    "RECORDING": "Recording…",
    "PROCESSING": "Processing…",
    "OUTPUTTING": "Outputting…",
    "ERROR": "Error",
}


class SystemTray(ABC):
    """System tray icon with state-based color updates."""

    STATE_COLORS = _STATE_COLORS
    STATE_LABELS = _STATE_LABELS

    @abstractmethod
    def start(self) -> None:
        """Start the tray icon (may spawn a thread)."""

    @abstractmethod
    def stop(self) -> None:
        """Shut down the tray."""

    @abstractmethod
    def on_state_change(self, state: SessionState) -> None:
        """Update tray appearance based on session state."""


class NullSystemTray(SystemTray):
    """No-op tray for platforms without support."""

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def on_state_change(self, state: SessionState) -> None:
        pass
