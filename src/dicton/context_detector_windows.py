"""Windows Context Detector for Dicton

Provides context detection on Windows using:
- pywin32 for window information (GetForegroundWindow, GetWindowText)
- comtypes/UIAutomation for widget focus detection
- psutil for process and terminal context
"""

import logging

from .context_detector import (
    ContextDetector,
    TerminalInfo,
    WidgetInfo,
    WindowInfo,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Windows Context Detector
# =============================================================================


class WindowsContextDetector(ContextDetector):
    """Context detector for Windows systems.

    Uses Win32 API via pywin32 for window detection and
    UI Automation API for widget-level focus detection.
    """

    def __init__(self):
        self._uia_client = None
        self._uia_available: bool | None = None

    def get_active_window(self) -> WindowInfo | None:
        """Get active window info using Win32 API."""
        try:
            import win32gui
            import win32process

            # Get foreground window handle
            hwnd = win32gui.GetForegroundWindow()
            if not hwnd:
                return None

            # Get window title
            title = win32gui.GetWindowText(hwnd)

            # Get window class name (equivalent to WM_CLASS on X11)
            wm_class = win32gui.GetClassName(hwnd)

            # Get process ID
            _, pid = win32process.GetWindowThreadProcessId(hwnd)

            # Get window geometry
            try:
                rect = win32gui.GetWindowRect(hwnd)
                geometry = (rect[0], rect[1], rect[2] - rect[0], rect[3] - rect[1])
            except Exception:
                geometry = None

            return WindowInfo(
                wm_class=wm_class,
                title=title,
                pid=pid,
                geometry=geometry,
            )

        except ImportError:
            logger.warning("pywin32 not installed - Windows context detection unavailable")
            return None
        except Exception as e:
            logger.debug(f"Windows window detection failed: {e}")
            return None

    def _init_uia(self) -> bool:
        """Initialize UI Automation client (lazy init)."""
        if self._uia_available is not None:
            return self._uia_available

        try:
            import comtypes.client

            # Initialize COM
            comtypes.CoInitialize()

            # Create UI Automation client
            self._uia_client = comtypes.client.CreateObject(
                "{ff48dba4-60ef-4201-aa87-54103eef594e}",  # CUIAutomation CLSID
                interface=None,
            )
            self._uia_available = True
            return True

        except ImportError:
            logger.debug("comtypes not available - UI Automation disabled")
            self._uia_available = False
        except Exception as e:
            logger.debug(f"UI Automation initialization failed: {e}")
            self._uia_available = False

        return False

    def get_widget_focus(self) -> WidgetInfo | None:
        """Get focused widget info via UI Automation API.

        Uses the Windows UI Automation framework to get detailed
        information about the focused element.
        """
        if not self._init_uia():
            return None

        try:
            # Get focused element
            focused = self._uia_client.GetFocusedElement()
            if not focused:
                return None

            # Get control type (role)
            control_type = focused.CurrentControlType
            role = self._control_type_to_role(control_type)

            # Get element name
            name = focused.CurrentName or ""

            # Get containing application
            try:
                # Walk up to find the root application element
                root = focused
                while root.CurrentParent:
                    parent = root.CurrentParent
                    if parent.CurrentControlType == 50032:  # UIA_WindowControlTypeId
                        break
                    root = parent
                app_name = root.CurrentName or ""
            except Exception:
                app_name = ""

            return WidgetInfo(
                role=role,
                name=name,
                application=app_name,
            )

        except Exception as e:
            logger.debug(f"UI Automation focus detection failed: {e}")
            return None

    def _control_type_to_role(self, control_type: int) -> str:
        """Convert UI Automation control type to role string."""
        # UI Automation control type IDs
        control_types = {
            50000: "button",
            50001: "calendar",
            50002: "checkbox",
            50003: "combobox",
            50004: "edit",  # Text edit
            50005: "hyperlink",
            50006: "image",
            50007: "listitem",
            50008: "list",
            50009: "menu",
            50010: "menubar",
            50011: "menuitem",
            50012: "progressbar",
            50013: "radiobutton",
            50014: "scrollbar",
            50015: "slider",
            50016: "spinner",
            50017: "statusbar",
            50018: "tab",
            50019: "tabitem",
            50020: "text",
            50021: "toolbar",
            50022: "tooltip",
            50023: "tree",
            50024: "treeitem",
            50025: "custom",
            50026: "group",
            50027: "thumb",
            50028: "datagrid",
            50029: "dataitem",
            50030: "document",
            50031: "splitbutton",
            50032: "window",
            50033: "pane",
            50034: "header",
            50035: "headeritem",
            50036: "table",
            50037: "titlebar",
            50038: "separator",
        }
        return control_types.get(control_type, f"unknown_{control_type}")

    def get_terminal_context(self) -> TerminalInfo | None:
        """Get terminal context for Windows terminals.

        Detects PowerShell, CMD, Windows Terminal, and WSL sessions.
        """
        window = self.get_active_window()
        if not window or not window.pid:
            return None

        # Check if it's a terminal-like application
        terminal_classes = {
            "CASCADIA_HOSTING_WINDOW_CLASS",  # Windows Terminal
            "ConsoleWindowClass",  # CMD/PowerShell legacy
            "mintty",  # Git Bash
            "PuTTY",  # PuTTY
        }

        if window.wm_class not in terminal_classes:
            return None

        try:
            import psutil

            term_proc = psutil.Process(window.pid)

            # Find shell process
            shell_name = ""
            cwd = ""

            for child in term_proc.children(recursive=True):
                try:
                    name = child.name().lower()
                    if name in (
                        "powershell.exe",
                        "pwsh.exe",
                        "cmd.exe",
                        "bash.exe",
                        "wsl.exe",
                        "zsh.exe",
                    ):
                        shell_name = name.replace(".exe", "")
                        cwd = child.cwd()
                        break
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            return TerminalInfo(
                shell=shell_name,
                cwd=cwd,
                running_command=None,  # Hard to detect on Windows
                session_type=None,
                session_name=None,
                pane_id=None,
            )

        except ImportError:
            logger.debug("psutil not available - terminal context unavailable")
        except Exception as e:
            logger.debug(f"Terminal context detection failed: {e}")

        return None

    def close(self):
        """Clean up UI Automation resources."""
        if self._uia_client:
            try:
                import comtypes

                comtypes.CoUninitialize()
            except Exception:
                pass
            self._uia_client = None
