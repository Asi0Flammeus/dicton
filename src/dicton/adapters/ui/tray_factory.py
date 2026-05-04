"""Factory for selecting the correct SystemTray implementation by platform."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from ...shared.platform_utils import IS_LINUX, IS_MACOS, IS_WINDOWS
from .tray_base import NullSystemTray, SystemTray

if TYPE_CHECKING:
    from collections.abc import Callable


def get_system_tray(
    *,
    on_quit: Callable[[], None],
    on_toggle_debug: Callable[[], bool],
    log_path: Path | None = None,
    config_port: int = 6873,
    initial_debug: bool = False,
) -> SystemTray:
    """Return the appropriate SystemTray for the current platform."""
    if IS_LINUX:
        try:
            from .tray_linux_gtk import GtkSystemTray

            return GtkSystemTray(
                on_quit=on_quit,
                on_toggle_debug=on_toggle_debug,
                log_path=log_path,
                config_port=config_port,
                initial_debug=initial_debug,
            )
        except ImportError:
            return NullSystemTray()
    if IS_WINDOWS:
        from .tray_windows import WindowsSystemTray

        return WindowsSystemTray(
            on_quit=on_quit,
            on_toggle_debug=on_toggle_debug,
            log_path=log_path,
            config_port=config_port,
            initial_debug=initial_debug,
        )
    if IS_MACOS:
        from .tray_macos import MacOSSystemTray

        return MacOSSystemTray()
    return NullSystemTray()
