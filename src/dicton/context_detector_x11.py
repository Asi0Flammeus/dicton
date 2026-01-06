"""X11 Context Detector for Dicton

Provides context detection on X11 display servers using:
- python-xlib for window information (primary)
- pyatspi for widget focus (optional, via system package)
- psutil + tmux CLI for terminal context enrichment
"""

import logging
import subprocess

from Xlib.display import Display

from .context_detector import (
    ContextDetector,
    TerminalInfo,
    WidgetInfo,
    WindowInfo,
)

logger = logging.getLogger(__name__)


# =============================================================================
# X11 Context Detector
# =============================================================================


class X11ContextDetector(ContextDetector):
    """Context detector for X11 display server.

    Uses python-xlib as the primary method for window detection,
    with optional pyatspi for widget-level focus detection.
    """

    def __init__(self):
        self._display: Display | None = None
        self._atspi_available: bool | None = None

    def _get_display(self) -> "Display":
        """Get or create X11 display connection (lazy init)."""
        if self._display is None:
            from Xlib import display

            self._display = display.Display()
        return self._display

    def _check_atspi(self) -> bool:
        """Check if AT-SPI is available (lazy init)."""
        if self._atspi_available is None:
            try:
                import pyatspi  # noqa: F401

                self._atspi_available = True
            except ImportError:
                logger.debug("pyatspi not available - widget focus detection disabled")
                self._atspi_available = False
        return self._atspi_available

    def get_active_window(self) -> WindowInfo | None:
        """Get active window info using X11.

        Uses _NET_ACTIVE_WINDOW property to find the focused window,
        then retrieves WM_CLASS and _NET_WM_NAME for identification.
        """
        try:
            d = self._get_display()
            root = d.screen().root

            # Get the active window atom
            net_active_window = d.intern_atom("_NET_ACTIVE_WINDOW")
            active_window_prop = root.get_full_property(net_active_window, 0)

            if not active_window_prop or not active_window_prop.value:
                return None

            window_id = active_window_prop.value[0]
            if window_id == 0:
                return None

            window = d.create_resource_object("window", window_id)

            # Get WM_CLASS (usually contains app name)
            wm_class = self._get_wm_class(window)

            # Get window title (_NET_WM_NAME or WM_NAME)
            title = self._get_window_title(window, d)

            # Get PID if available
            pid = self._get_window_pid(window, d)

            # Get geometry
            geometry = self._get_window_geometry(window)

            return WindowInfo(
                wm_class=wm_class,
                title=title,
                pid=pid,
                geometry=geometry,
            )

        except Exception as e:
            logger.warning(f"X11 window detection failed: {e}")
            return None

    def _get_wm_class(self, window) -> str:
        """Extract WM_CLASS property from window."""
        try:
            wm_class = window.get_wm_class()
            if wm_class:
                # WM_CLASS returns (instance, class) tuple
                # Use class name (second element) as it's more consistent
                return wm_class[1] if len(wm_class) > 1 else wm_class[0]
        except Exception:
            pass
        return ""

    def _get_window_title(self, window, display: "Display") -> str:
        """Get window title, preferring _NET_WM_NAME over WM_NAME."""
        try:
            # Try _NET_WM_NAME first (UTF-8)
            net_wm_name = display.intern_atom("_NET_WM_NAME")
            utf8_string = display.intern_atom("UTF8_STRING")
            prop = window.get_full_property(net_wm_name, utf8_string)
            if prop and prop.value:
                return prop.value.decode("utf-8", errors="replace")

            # Fall back to WM_NAME
            wm_name = window.get_wm_name()
            if wm_name:
                if isinstance(wm_name, bytes):
                    return wm_name.decode("utf-8", errors="replace")
                return wm_name
        except Exception:
            pass
        return ""

    def _get_window_pid(self, window, display: "Display") -> int | None:
        """Get process ID from _NET_WM_PID property."""
        try:
            net_wm_pid = display.intern_atom("_NET_WM_PID")
            prop = window.get_full_property(net_wm_pid, 0)
            if prop and prop.value:
                return prop.value[0]
        except Exception:
            pass
        return None

    def _get_window_geometry(self, window) -> tuple[int, int, int, int] | None:
        """Get window geometry (x, y, width, height)."""
        try:
            geom = window.get_geometry()
            return (geom.x, geom.y, geom.width, geom.height)
        except Exception:
            pass
        return None

    def get_widget_focus(self) -> WidgetInfo | None:
        """Get focused widget info via AT-SPI accessibility API.

        Requires python3-pyatspi system package. Returns None if
        AT-SPI is not available or if no focused widget is found.
        """
        if not self._check_atspi():
            return None

        try:
            import pyatspi

            # Get the desktop (top-level accessible)
            desktop = pyatspi.Registry.getDesktop(0)
            if not desktop:
                return None

            # Find focused application
            for app in desktop:
                if not app:
                    continue

                # Check each window in the application
                for window in app:
                    if not window:
                        continue

                    # Find focused widget recursively
                    focused = self._find_focused_widget(window)
                    if focused:
                        role = pyatspi.getRoleName(focused)
                        name = focused.name or ""

                        # Get surrounding text if it's a text widget
                        caret_pos = None
                        surrounding = None
                        if self._is_text_widget(focused):
                            try:
                                text_iface = focused.queryText()
                                caret_pos = text_iface.caretOffset
                                # Get some text around caret
                                start = max(0, caret_pos - 50)
                                end = caret_pos + 50
                                surrounding = text_iface.getText(start, end)
                            except Exception:
                                pass

                        return WidgetInfo(
                            role=role,
                            name=name,
                            application=app.name or "",
                            caret_position=caret_pos,
                            surrounding_text=surrounding,
                        )

        except Exception as e:
            logger.debug(f"AT-SPI widget focus detection failed: {e}")

        return None

    def _find_focused_widget(self, accessible):
        """Recursively find the focused widget in the accessibility tree."""
        try:
            import pyatspi

            # Check if this accessible has focus
            state_set = accessible.getState()
            if state_set.contains(pyatspi.STATE_FOCUSED):
                return accessible

            # Check children
            for child in accessible:
                if not child:
                    continue
                result = self._find_focused_widget(child)
                if result:
                    return result

        except Exception:
            pass

        return None

    def _is_text_widget(self, accessible) -> bool:
        """Check if accessible implements text interface."""
        try:
            import pyatspi

            role = accessible.getRole()
            text_roles = {
                pyatspi.ROLE_TEXT,
                pyatspi.ROLE_ENTRY,
                pyatspi.ROLE_PARAGRAPH,
                pyatspi.ROLE_TERMINAL,
                pyatspi.ROLE_DOCUMENT_TEXT,
            }
            return role in text_roles
        except Exception:
            return False

    def get_terminal_context(self) -> TerminalInfo | None:
        """Get terminal context from process tree and tmux/screen.

        Enriches context when the active window is a terminal emulator
        by detecting shell type, current directory, and multiplexer session.
        """
        window = self.get_active_window()
        if not window or not window.pid:
            return None

        try:
            import psutil

            # Get the terminal process
            term_proc = psutil.Process(window.pid)

            # Find the shell process (child of terminal)
            shell_proc = None
            shell_name = ""
            cwd = ""

            for child in term_proc.children(recursive=True):
                try:
                    name = child.name().lower()
                    if name in ("bash", "zsh", "fish", "sh", "tcsh", "csh", "dash"):
                        shell_proc = child
                        shell_name = name
                        cwd = child.cwd()
                        break
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            # Check for running command (child of shell)
            running_cmd = None
            if shell_proc:
                try:
                    for child in shell_proc.children():
                        cmdline = child.cmdline()
                        if cmdline:
                            running_cmd = " ".join(cmdline[:3])  # First 3 args
                            break
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            # Check for tmux/screen session
            session_type = None
            session_name = None
            pane_id = None

            # Check tmux
            tmux_info = self._get_tmux_info()
            if tmux_info:
                session_type = "tmux"
                session_name = tmux_info.get("session")
                pane_id = tmux_info.get("pane")
                # tmux pane may have more accurate cwd
                if tmux_info.get("cwd"):
                    cwd = tmux_info["cwd"]

            return TerminalInfo(
                shell=shell_name,
                cwd=cwd,
                running_command=running_cmd,
                session_type=session_type,
                session_name=session_name,
                pane_id=pane_id,
            )

        except Exception as e:
            logger.debug(f"Terminal context detection failed: {e}")
            return None

    def _get_tmux_info(self) -> dict | None:
        """Get tmux session information if inside tmux."""
        try:
            # Check if we're in tmux
            result = subprocess.run(
                ["tmux", "display-message", "-p", "#{session_name}:#{window_index}.#{pane_index}"],
                capture_output=True,
                text=True,
                timeout=1,
            )
            if result.returncode == 0 and result.stdout.strip():
                parts = result.stdout.strip().split(":")
                if len(parts) >= 2:
                    session = parts[0]
                    pane = parts[1]

                    # Get pane CWD
                    cwd_result = subprocess.run(
                        ["tmux", "display-message", "-p", "#{pane_current_path}"],
                        capture_output=True,
                        text=True,
                        timeout=1,
                    )
                    cwd = cwd_result.stdout.strip() if cwd_result.returncode == 0 else ""

                    return {
                        "session": session,
                        "pane": pane,
                        "cwd": cwd,
                    }
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        return None

    def close(self):
        """Close the X11 display connection."""
        if self._display:
            try:
                self._display.close()
            except Exception:
                pass
            self._display = None
