"""Context Detection Module for Dicton

Provides platform-aware detection of active window, widget focus, and terminal context
to enable context-aware LLM prompts and adaptive behavior.

Architecture: Graceful degradation with fallback chain:
  Level 1: Widget Focus (AT-SPI) - Most precise
  Level 2: Pane/Session Context (tmux, terminal process)
  Level 3: Window Title - Minimum viable (always available)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


class DisplayServer(Enum):
    """Display server types for Linux."""

    X11 = "x11"
    WAYLAND = "wayland"
    UNKNOWN = "unknown"


class Platform(Enum):
    """Operating system platforms."""

    LINUX = "linux"
    WINDOWS = "windows"
    MACOS = "macos"
    UNKNOWN = "unknown"


@dataclass
class WindowInfo:
    """Information about the active window.

    Attributes:
        wm_class: Window manager class (e.g., "firefox", "code", "gnome-terminal")
        title: Window title (e.g., "main.py - Visual Studio Code")
        pid: Process ID of the window's application
        geometry: Optional window geometry (x, y, width, height)
    """

    wm_class: str
    title: str
    pid: int | None = None
    geometry: tuple[int, int, int, int] | None = None

    @property
    def app_name(self) -> str:
        """Extract application name from wm_class."""
        return self.wm_class.lower().split(".")[-1] if self.wm_class else ""

    def matches_class(self, *classes: str) -> bool:
        """Check if wm_class matches any of the given class names."""
        app = self.app_name
        return any(cls.lower() in app for cls in classes)

    def title_contains(self, *substrings: str) -> bool:
        """Check if window title contains any of the given substrings."""
        title_lower = self.title.lower()
        return any(s.lower() in title_lower for s in substrings)


@dataclass
class WidgetInfo:
    """Information about the focused widget (via accessibility API).

    Attributes:
        role: Widget role (e.g., "text", "entry", "terminal", "editor")
        name: Widget name or label
        application: Parent application name
        caret_position: Text caret position if applicable
        surrounding_text: Text around the caret if accessible
    """

    role: str
    name: str = ""
    application: str = ""
    caret_position: int | None = None
    surrounding_text: str | None = None

    def is_text_entry(self) -> bool:
        """Check if widget is a text entry field."""
        text_roles = {"text", "entry", "text entry", "editor", "document", "terminal"}
        return self.role.lower() in text_roles


@dataclass
class TerminalInfo:
    """Information about terminal/shell context.

    Attributes:
        shell: Current shell (bash, zsh, fish, etc.)
        cwd: Current working directory
        running_command: Currently running command (if any)
        session_type: Terminal multiplexer type (tmux, screen, none)
        session_name: Multiplexer session name
        pane_id: Multiplexer pane identifier
    """

    shell: str = ""
    cwd: str = ""
    running_command: str | None = None
    session_type: str | None = None  # "tmux", "screen", None
    session_name: str | None = None
    pane_id: str | None = None


@dataclass
class ContextInfo:
    """Combined context information from all detection levels.

    This is the primary data structure passed to LLM processors
    for context-aware prompt generation.
    """

    window: WindowInfo | None = None
    widget: WidgetInfo | None = None
    terminal: TerminalInfo | None = None
    profile_name: str | None = None  # Matched profile from contexts.json
    detection_level: int = 3  # 1=widget, 2=terminal, 3=window (fallback)
    errors: list[str] = field(default_factory=list)

    @property
    def is_terminal(self) -> bool:
        """Check if context is a terminal application."""
        if self.widget and self.widget.role.lower() == "terminal":
            return True
        if self.window and self.window.matches_class(
            "gnome-terminal",
            "konsole",
            "kitty",
            "alacritty",
            "terminator",
            "xterm",
            "tilix",
            "wezterm",
        ):
            return True
        return False

    @property
    def is_editor(self) -> bool:
        """Check if context is a code editor."""
        if self.widget and self.widget.role.lower() in ("editor", "document"):
            return True
        if self.window and self.window.matches_class(
            "code", "vscode", "pycharm", "idea", "sublime", "atom", "vim", "nvim", "emacs"
        ):
            return True
        return False

    @property
    def app_name(self) -> str:
        """Get the application name from best available source."""
        if self.widget and self.widget.application:
            return self.widget.application
        if self.window:
            return self.window.app_name
        return ""


class ContextDetector(ABC):
    """Abstract base class for platform-specific context detection.

    Implementations should provide detection for:
    - Active window (required)
    - Widget focus (optional, AT-SPI/UI Automation)
    - Terminal context (optional, for shell environments)

    The detection follows a graceful degradation pattern:
    1. Try widget focus detection (most precise)
    2. Fall back to terminal context if in shell
    3. Always return at least window info (minimum viable)
    """

    @abstractmethod
    def get_active_window(self) -> WindowInfo | None:
        """Get information about the currently active/focused window.

        Returns:
            WindowInfo with wm_class, title, and optionally pid/geometry.
            Returns None if detection fails completely.
        """
        pass

    @abstractmethod
    def get_widget_focus(self) -> WidgetInfo | None:
        """Get information about the focused widget via accessibility API.

        This provides the most precise context (specific text field, editor, etc.)
        but may not be available on all platforms or applications.

        Returns:
            WidgetInfo if accessibility API is available and widget is focused.
            Returns None if not available or detection fails.
        """
        pass

    @abstractmethod
    def get_terminal_context(self) -> TerminalInfo | None:
        """Get terminal/shell context if current window is a terminal.

        Enriches context with shell information, current directory,
        and tmux/screen session details if applicable.

        Returns:
            TerminalInfo if in a terminal context.
            Returns None if not in terminal or detection fails.
        """
        pass

    def get_context(self) -> ContextInfo:
        """Get complete context using fallback chain.

        Attempts detection at each level and returns the most complete
        context available. Errors at each level are captured but don't
        prevent fallback to less precise detection.

        Returns:
            ContextInfo with best available information from all levels.
        """
        context = ContextInfo()

        # Level 3: Window info (minimum viable, always attempted)
        try:
            context.window = self.get_active_window()
            if context.window:
                context.detection_level = 3
        except Exception as e:
            context.errors.append(f"Window detection failed: {e}")

        # Level 2: Terminal context (if window is terminal-like)
        if context.is_terminal:
            try:
                context.terminal = self.get_terminal_context()
                if context.terminal:
                    context.detection_level = 2
            except Exception as e:
                context.errors.append(f"Terminal context failed: {e}")

        # Level 1: Widget focus (most precise)
        try:
            context.widget = self.get_widget_focus()
            if context.widget:
                context.detection_level = 1
        except Exception as e:
            context.errors.append(f"Widget focus failed: {e}")

        return context


class NullContextDetector(ContextDetector):
    """Null implementation that returns no context.

    Used when context detection is disabled or unavailable.
    """

    def get_active_window(self) -> WindowInfo | None:
        return None

    def get_widget_focus(self) -> WidgetInfo | None:
        return None

    def get_terminal_context(self) -> TerminalInfo | None:
        return None


# =============================================================================
# Factory Function
# =============================================================================

_cached_detector: ContextDetector | None = None


def get_context_detector(force_type: str | None = None) -> ContextDetector:
    """Get the appropriate context detector for the current platform.

    Uses lazy initialization and caches the detector instance.

    Args:
        force_type: Force a specific detector type for testing.
                   Options: "x11", "wayland", "windows", "null"

    Returns:
        ContextDetector implementation appropriate for the platform.
    """
    global _cached_detector

    if _cached_detector is not None and force_type is None:
        return _cached_detector

    if force_type == "null":
        return NullContextDetector()

    # Import platform detection
    from .platform_utils import IS_LINUX, IS_WAYLAND, IS_WINDOWS, IS_X11

    detector: ContextDetector

    if force_type == "x11" or (IS_LINUX and IS_X11 and force_type is None):
        try:
            from .context_detector_x11 import X11ContextDetector

            detector = X11ContextDetector()
        except ImportError as e:
            import logging

            logging.warning(f"X11 context detector unavailable: {e}")
            detector = NullContextDetector()

    elif force_type == "wayland" or (IS_LINUX and IS_WAYLAND and force_type is None):
        try:
            from .context_detector_wayland import WaylandContextDetector

            detector = WaylandContextDetector()
        except ImportError as e:
            import logging

            logging.warning(f"Wayland context detector unavailable: {e}")
            detector = NullContextDetector()

    elif force_type == "windows" or (IS_WINDOWS and force_type is None):
        try:
            from .context_detector_windows import WindowsContextDetector

            detector = WindowsContextDetector()
        except ImportError as e:
            import logging

            logging.warning(f"Windows context detector unavailable: {e}")
            detector = NullContextDetector()

    else:
        # Unsupported platform or macOS (not yet implemented)
        detector = NullContextDetector()

    if force_type is None:
        _cached_detector = detector

    return detector


def clear_detector_cache():
    """Clear the cached detector instance.

    Useful for testing or when display server changes.
    """
    global _cached_detector
    _cached_detector = None
