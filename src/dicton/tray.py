"""System tray icon for Dicton using AyatanaAppIndicator3.

Provides a persistent tray presence with:
- Color-coded state indicator (idle/recording/processing/error)
- Debug mode toggle
- Quick access to log file and settings
- Clean quit action

Gracefully degrades to a no-op if GTK/AppIndicator is not installed.
"""

from __future__ import annotations

import hashlib
import logging
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import TYPE_CHECKING

from .core.state_machine import SessionState

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)

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

_ICON_SIZE = 24
_icon_cache: dict[str, str] = {}


def _generate_icon(hex_color: str) -> str:
    """Generate a colored circle PNG via Cairo, return path. Cached per color."""
    if hex_color in _icon_cache:
        return _icon_cache[hex_color]

    try:
        import cairo
    except ImportError:
        import cairocffi as cairo  # type: ignore[no-redefine]

    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, _ICON_SIZE, _ICON_SIZE)
    ctx = cairo.Context(surface)

    # Parse hex color
    r = int(hex_color[1:3], 16) / 255.0
    g = int(hex_color[3:5], 16) / 255.0
    b = int(hex_color[5:7], 16) / 255.0

    # Draw filled circle
    ctx.arc(_ICON_SIZE / 2, _ICON_SIZE / 2, _ICON_SIZE / 2 - 1, 0, 2 * 3.14159265)
    ctx.set_source_rgb(r, g, b)
    ctx.fill()

    # Save to temp file (stable name per color so we don't leak files)
    color_hash = hashlib.md5(hex_color.encode()).hexdigest()[:8]  # noqa: S324
    path = Path(tempfile.gettempdir()) / f"dicton-tray-{color_hash}.png"
    surface.write_to_png(str(path))

    _icon_cache[hex_color] = str(path)
    return str(path)


class DictonTray:
    """System tray icon backed by AyatanaAppIndicator3.

    All GTK interactions happen on a dedicated daemon thread.
    State updates are marshalled via ``GLib.idle_add()``.
    """

    def __init__(
        self,
        *,
        on_quit: Callable[[], None],
        on_toggle_debug: Callable[[], bool],
        log_path: Path | None = None,
        config_port: int = 6873,
    ):
        self._on_quit = on_quit
        self._on_toggle_debug = on_toggle_debug
        self._log_path = log_path
        self._config_port = config_port
        self._indicator = None
        self._status_item = None
        self._debug_item = None
        self._gtk_thread: threading.Thread | None = None
        self._started = False

    # -- Public API -------------------------------------------------------

    def start(self) -> None:
        """Spin up the GTK main loop in a daemon thread."""
        self._gtk_thread = threading.Thread(target=self._run_gtk, daemon=True, name="dicton-tray")
        self._gtk_thread.start()

    def on_state_change(self, state: SessionState) -> None:
        """Observer callback — called from any thread on state transitions."""
        if not self._started:
            return
        try:
            from gi.repository import GLib

            GLib.idle_add(self._update_state, state)
        except Exception:
            pass

    # -- GTK thread -------------------------------------------------------

    def _run_gtk(self) -> None:
        try:
            import gi

            gi.require_version("Gtk", "3.0")
            gi.require_version("AyatanaAppIndicator3", "0.1")
            from gi.repository import AyatanaAppIndicator3, Gtk

            icon_path = _generate_icon(_STATE_COLORS["IDLE"])

            self._indicator = AyatanaAppIndicator3.Indicator.new(
                "dicton",
                icon_path,
                AyatanaAppIndicator3.IndicatorCategory.APPLICATION_STATUS,
            )
            self._indicator.set_status(AyatanaAppIndicator3.IndicatorStatus.ACTIVE)
            self._indicator.set_menu(self._build_menu(Gtk))

            self._started = True
            logger.debug("System tray started")
            Gtk.main()
        except Exception:
            logger.debug("System tray unavailable", exc_info=True)

    def _build_menu(self, Gtk):  # noqa: N803
        menu = Gtk.Menu()

        # Status label (not clickable)
        self._status_item = Gtk.MenuItem(label="Dicton — Idle")
        self._status_item.set_sensitive(False)
        menu.append(self._status_item)

        menu.append(Gtk.SeparatorMenuItem())

        # Debug toggle
        from .config import config

        debug_label = f"Debug mode: {'ON' if config.DEBUG else 'OFF'}"
        self._debug_item = Gtk.MenuItem(label=debug_label)
        self._debug_item.connect("activate", self._on_debug_clicked)
        menu.append(self._debug_item)

        menu.append(Gtk.SeparatorMenuItem())

        # Open Settings
        settings_item = Gtk.MenuItem(label="Open Settings")
        settings_item.connect("activate", self._on_settings_clicked)
        menu.append(settings_item)

        # View Log
        if self._log_path:
            log_item = Gtk.MenuItem(label="View Log")
            log_item.connect("activate", self._on_view_log_clicked)
            menu.append(log_item)

        menu.append(Gtk.SeparatorMenuItem())

        # Quit
        quit_item = Gtk.MenuItem(label="Quit")
        quit_item.connect("activate", self._on_quit_clicked)
        menu.append(quit_item)

        menu.show_all()
        return menu

    # -- State updates (GTK thread via idle_add) --------------------------

    def _update_state(self, state: SessionState) -> bool:
        """Update icon and label. Returns False to remove from idle queue."""
        name = state.name
        color = _STATE_COLORS.get(name, _STATE_COLORS["IDLE"])
        label = _STATE_LABELS.get(name, name)

        if self._indicator:
            icon_path = _generate_icon(color)
            self._indicator.set_icon_full(icon_path, f"Dicton — {label}")

        if self._status_item:
            self._status_item.set_label(f"Dicton — {label}")

        return False  # remove from idle queue

    # -- Menu callbacks (GTK thread) --------------------------------------

    def _on_debug_clicked(self, _widget) -> None:
        is_debug = self._on_toggle_debug()
        if self._debug_item:
            self._debug_item.set_label(f"Debug mode: {'ON' if is_debug else 'OFF'}")

    def _on_settings_clicked(self, _widget) -> None:
        try:
            subprocess.Popen(  # noqa: S603
                ["dicton", "--config-ui", "--config-port", str(self._config_port)],
                start_new_session=True,
            )
        except FileNotFoundError:
            logger.warning("Could not launch dicton --config-ui")

    def _on_view_log_clicked(self, _widget) -> None:
        if self._log_path and self._log_path.exists():
            try:
                subprocess.Popen(["xdg-open", str(self._log_path)], start_new_session=True)  # noqa: S603
            except FileNotFoundError:
                logger.warning("xdg-open not found")

    def _on_quit_clicked(self, _widget) -> None:
        self._on_quit()
        try:
            from gi.repository import Gtk

            Gtk.main_quit()
        except Exception:
            pass

    def stop(self) -> None:
        """Shut down the GTK main loop."""
        if not self._started:
            return
        try:
            from gi.repository import GLib, Gtk

            GLib.idle_add(Gtk.main_quit)
        except Exception:
            pass
