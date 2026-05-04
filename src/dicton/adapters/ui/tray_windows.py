"""Windows system tray for Dicton using pystray."""

from __future__ import annotations

import logging
import subprocess
import sys
import threading
from pathlib import Path
from typing import TYPE_CHECKING

from ...core.state_machine import SessionState
from .tray_base import SystemTray

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)
_ICON_SIZE = 64


def _build_icon(hex_color: str):
    """Build a simple colored circular tray icon."""
    from PIL import Image, ImageDraw

    image = Image.new("RGBA", (_ICON_SIZE, _ICON_SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((6, 6, _ICON_SIZE - 6, _ICON_SIZE - 6), fill=hex_color)
    return image


class WindowsSystemTray(SystemTray):
    """Windows tray icon with settings, logs, debug toggle, and quit actions."""

    def __init__(
        self,
        *,
        on_quit: Callable[[], None],
        on_toggle_debug: Callable[[], bool],
        log_path: Path | None = None,
        config_port: int = 6873,
        initial_debug: bool = False,
    ):
        self._on_quit = on_quit
        self._on_toggle_debug = on_toggle_debug
        self._log_path = log_path
        self._config_port = config_port
        self._debug = initial_debug
        self._state_label = self.STATE_LABELS["IDLE"]
        self._icon = None
        self._thread: threading.Thread | None = None
        self._started = False

    def start(self) -> None:
        try:
            import pystray

            self._icon = pystray.Icon(
                "dicton",
                _build_icon(self.STATE_COLORS["IDLE"]),
                "Dicton — Idle",
                self._build_menu(),
            )
            self._thread = threading.Thread(target=self._icon.run, daemon=True, name="dicton-tray")
            self._thread.start()
            self._started = True
        except Exception:
            logger.debug("Windows tray unavailable", exc_info=True)

    def stop(self) -> None:
        if self._icon is not None:
            try:
                self._icon.stop()
            except Exception:
                logger.debug("Failed to stop Windows tray", exc_info=True)
        self._started = False

    def on_state_change(self, state: SessionState) -> None:
        if not self._started or self._icon is None:
            return

        name = state.name
        color = self.STATE_COLORS.get(name, self.STATE_COLORS["IDLE"])
        self._state_label = self.STATE_LABELS.get(name, name)

        try:
            self._icon.icon = _build_icon(color)
            self._icon.title = f"Dicton — {self._state_label}"
            self._icon.menu = self._build_menu()
            self._icon.update_menu()
        except Exception:
            logger.debug("Failed to update Windows tray state", exc_info=True)

    def _build_menu(self):
        import pystray

        items = [
            pystray.MenuItem(f"Dicton — {self._state_label}", None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Open Setup", self._open_setup),
            pystray.MenuItem("View Log", self._view_log, enabled=self._log_path_exists),
            pystray.MenuItem(
                lambda _item: f"Debug mode: {'ON' if self._debug else 'OFF'}",
                self._toggle_debug,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self._quit),
        ]
        return pystray.Menu(*items)

    def _log_path_exists(self, _item) -> bool:
        return bool(self._log_path and self._log_path.exists())

    def _open_setup(self, _icon=None, _item=None) -> None:
        cmd = [sys.executable, "--config", "--config-port", str(self._config_port)]
        try:
            subprocess.Popen(  # noqa: S603
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
            )
        except Exception:
            logger.warning("Could not launch Dicton setup", exc_info=True)

    def _view_log(self, _icon=None, _item=None) -> None:
        if not self._log_path or not self._log_path.exists():
            return
        try:
            subprocess.Popen(["explorer", str(self._log_path)])  # noqa: S603, S607
        except Exception:
            logger.warning("Could not open Dicton log", exc_info=True)

    def _toggle_debug(self, _icon=None, _item=None) -> None:
        self._debug = self._on_toggle_debug()
        if self._icon is not None:
            self._icon.update_menu()

    def _quit(self, _icon=None, _item=None) -> None:
        self._on_quit()
        self.stop()
