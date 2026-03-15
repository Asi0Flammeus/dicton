"""Windows system tray stub for Dicton."""

from __future__ import annotations

from ..core.state_machine import SessionState
from .tray_base import SystemTray


class WindowsSystemTray(SystemTray):
    """Windows tray icon — not yet implemented (future: pystray or win32gui)."""

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def on_state_change(self, state: SessionState) -> None:
        pass
