"""macOS system tray stub for Dicton."""

from __future__ import annotations

from ..core.state_machine import SessionState
from .tray_base import SystemTray


class MacOSSystemTray(SystemTray):
    """macOS menu bar icon — not yet implemented (future: rumps or PyObjC)."""

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def on_state_change(self, state: SessionState) -> None:
        pass
