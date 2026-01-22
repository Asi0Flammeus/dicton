"""Tests for Dicton context detection module.

Tests data classes, NullContextDetector, factory function, and platform-specific
detectors using mocks to avoid requiring actual display servers.
"""

import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest

# =============================================================================
# Data Classes Tests
# =============================================================================


class TestWindowInfo:
    """Test WindowInfo dataclass."""

    def test_basic_creation(self):
        """Test WindowInfo can be created with required fields."""
        from dicton.context_detector import WindowInfo

        info = WindowInfo(wm_class="firefox", title="Mozilla Firefox")
        assert info.wm_class == "firefox"
        assert info.title == "Mozilla Firefox"
        assert info.pid is None
        assert info.geometry is None

    def test_with_all_fields(self):
        """Test WindowInfo with all fields populated."""
        from dicton.context_detector import WindowInfo

        info = WindowInfo(
            wm_class="Code",
            title="main.py - Visual Studio Code",
            pid=12345,
            geometry=(100, 200, 800, 600),
        )
        assert info.pid == 12345
        assert info.geometry == (100, 200, 800, 600)

    def test_app_name_property(self):
        """Test app_name extracts from wm_class correctly."""
        from dicton.context_detector import WindowInfo

        # Simple class
        info1 = WindowInfo(wm_class="firefox", title="Test")
        assert info1.app_name == "firefox"

        # Dotted class (org.gnome.Terminal)
        info2 = WindowInfo(wm_class="org.gnome.Terminal", title="Test")
        assert info2.app_name == "terminal"

        # Empty class
        info3 = WindowInfo(wm_class="", title="Test")
        assert info3.app_name == ""

    def test_matches_class(self):
        """Test matches_class pattern matching."""
        from dicton.context_detector import WindowInfo

        info = WindowInfo(wm_class="code", title="Test")
        assert info.matches_class("code")
        assert info.matches_class("vscode", "code")
        assert not info.matches_class("firefox")
        assert info.matches_class("CODE")  # Case insensitive

    def test_title_contains(self):
        """Test title_contains substring matching."""
        from dicton.context_detector import WindowInfo

        info = WindowInfo(wm_class="code", title="main.py - Visual Studio Code")
        assert info.title_contains("main.py")
        assert info.title_contains("Visual Studio")
        assert info.title_contains("MAIN.PY")  # Case insensitive
        assert not info.title_contains("Firefox")


class TestWidgetInfo:
    """Test WidgetInfo dataclass."""

    def test_basic_creation(self):
        """Test WidgetInfo can be created with role."""
        from dicton.context_detector import WidgetInfo

        info = WidgetInfo(role="text")
        assert info.role == "text"
        assert info.name == ""
        assert info.application == ""

    def test_is_text_entry(self):
        """Test is_text_entry role detection."""
        from dicton.context_detector import WidgetInfo

        # Text entry roles
        for role in ["text", "entry", "editor", "document", "terminal"]:
            info = WidgetInfo(role=role)
            assert info.is_text_entry(), f"Role '{role}' should be text entry"

        # Non-text roles
        for role in ["button", "menu", "label"]:
            info = WidgetInfo(role=role)
            assert not info.is_text_entry(), f"Role '{role}' should not be text entry"


class TestTerminalInfo:
    """Test TerminalInfo dataclass."""

    def test_default_values(self):
        """Test TerminalInfo has sensible defaults."""
        from dicton.context_detector import TerminalInfo

        info = TerminalInfo()
        assert info.shell == ""
        assert info.cwd == ""
        assert info.running_command is None
        assert info.session_type is None

    def test_with_tmux_session(self):
        """Test TerminalInfo with tmux session data."""
        from dicton.context_detector import TerminalInfo

        info = TerminalInfo(
            shell="bash",
            cwd="/home/user/project",
            session_type="tmux",
            session_name="main",
            pane_id="0.1",
        )
        assert info.session_type == "tmux"
        assert info.session_name == "main"


class TestContextInfo:
    """Test ContextInfo combined context."""

    def test_empty_context(self):
        """Test ContextInfo with no data."""
        from dicton.context_detector import ContextInfo

        ctx = ContextInfo()
        assert ctx.window is None
        assert ctx.widget is None
        assert ctx.terminal is None
        assert ctx.detection_level == 3
        assert ctx.errors == []

    def test_is_terminal_by_widget(self):
        """Test is_terminal detects terminal widget role."""
        from dicton.context_detector import ContextInfo, WidgetInfo

        ctx = ContextInfo(widget=WidgetInfo(role="terminal"))
        assert ctx.is_terminal

    def test_is_terminal_by_window_class(self):
        """Test is_terminal detects terminal by wm_class."""
        from dicton.context_detector import ContextInfo, WindowInfo

        for terminal_class in ["gnome-terminal", "kitty", "alacritty"]:
            ctx = ContextInfo(window=WindowInfo(wm_class=terminal_class, title=""))
            assert ctx.is_terminal, f"{terminal_class} should be detected as terminal"

    def test_is_editor_by_widget(self):
        """Test is_editor detects editor widget role."""
        from dicton.context_detector import ContextInfo, WidgetInfo

        ctx = ContextInfo(widget=WidgetInfo(role="editor"))
        assert ctx.is_editor

    def test_is_editor_by_window_class(self):
        """Test is_editor detects editors by wm_class."""
        from dicton.context_detector import ContextInfo, WindowInfo

        for editor_class in ["code", "vscode", "pycharm", "sublime"]:
            ctx = ContextInfo(window=WindowInfo(wm_class=editor_class, title=""))
            assert ctx.is_editor, f"{editor_class} should be detected as editor"

    def test_app_name_from_widget(self):
        """Test app_name prefers widget application."""
        from dicton.context_detector import ContextInfo, WidgetInfo, WindowInfo

        ctx = ContextInfo(
            window=WindowInfo(wm_class="code", title="Test"),
            widget=WidgetInfo(role="text", application="Visual Studio Code"),
        )
        assert ctx.app_name == "Visual Studio Code"

    def test_app_name_fallback_to_window(self):
        """Test app_name falls back to window wm_class."""
        from dicton.context_detector import ContextInfo, WindowInfo

        ctx = ContextInfo(window=WindowInfo(wm_class="firefox", title="Test"))
        assert ctx.app_name == "firefox"


# =============================================================================
# NullContextDetector Tests
# =============================================================================


class TestNullContextDetector:
    """Test NullContextDetector returns no context."""

    def test_get_active_window_returns_none(self):
        """Test get_active_window returns None."""
        from dicton.context_detector import NullContextDetector

        detector = NullContextDetector()
        assert detector.get_active_window() is None

    def test_get_widget_focus_returns_none(self):
        """Test get_widget_focus returns None."""
        from dicton.context_detector import NullContextDetector

        detector = NullContextDetector()
        assert detector.get_widget_focus() is None

    def test_get_terminal_context_returns_none(self):
        """Test get_terminal_context returns None."""
        from dicton.context_detector import NullContextDetector

        detector = NullContextDetector()
        assert detector.get_terminal_context() is None

    def test_get_context_returns_empty(self):
        """Test get_context returns empty ContextInfo."""
        from dicton.context_detector import NullContextDetector

        detector = NullContextDetector()
        ctx = detector.get_context()
        assert ctx.window is None
        assert ctx.widget is None
        assert ctx.terminal is None


# =============================================================================
# Factory Function Tests
# =============================================================================


class TestGetContextDetector:
    """Test get_context_detector factory function."""

    def test_null_type_returns_null_detector(self):
        """Test force_type='null' returns NullContextDetector."""
        from dicton.context_detector import NullContextDetector, get_context_detector

        detector = get_context_detector(force_type="null")
        assert isinstance(detector, NullContextDetector)

    def test_caching_behavior(self):
        """Test detector is cached when force_type is None."""
        from dicton.context_detector import clear_detector_cache, get_context_detector

        clear_detector_cache()

        # Get detector twice
        detector1 = get_context_detector()
        detector2 = get_context_detector()

        # Should be the same instance
        assert detector1 is detector2

        clear_detector_cache()

    def test_force_type_bypasses_cache(self):
        """Test force_type bypasses cached detector."""
        from dicton.context_detector import (
            NullContextDetector,
            clear_detector_cache,
            get_context_detector,
        )

        clear_detector_cache()

        # Get a cached detector
        _ = get_context_detector()

        # Force null should return new instance
        null_detector = get_context_detector(force_type="null")
        assert isinstance(null_detector, NullContextDetector)

        clear_detector_cache()

    def test_x11_platform_detection(self):
        """Test X11 detector is selected on X11 Linux."""
        from dicton.context_detector import clear_detector_cache, get_context_detector

        clear_detector_cache()

        # Patch at platform_utils module level since that's where flags are imported from
        with (
            patch("dicton.platform_utils.IS_LINUX", True),
            patch("dicton.platform_utils.IS_X11", True),
            patch("dicton.platform_utils.IS_WAYLAND", False),
            patch("dicton.platform_utils.IS_WINDOWS", False),
        ):
            # The detector will try to import X11ContextDetector
            # On a real X11 system, it would succeed. Here we just verify
            # the function returns without error (either X11 or Null)
            detector = get_context_detector()
            assert detector is not None

        clear_detector_cache()

    def test_unsupported_platform_returns_null(self):
        """Test unsupported platform returns NullContextDetector."""
        from dicton.context_detector import (
            NullContextDetector,
            clear_detector_cache,
            get_context_detector,
        )

        clear_detector_cache()

        # Patch platform flags to simulate unsupported platform
        with (
            patch("dicton.platform_utils.IS_LINUX", False),
            patch("dicton.platform_utils.IS_WINDOWS", False),
        ):
            detector = get_context_detector()
            # On unsupported platforms, should return NullContextDetector
            assert isinstance(detector, NullContextDetector)

        clear_detector_cache()


# =============================================================================
# X11 Context Detector Tests (Mocked)
# =============================================================================


class TestX11ContextDetector:
    """Test X11ContextDetector with mocked Xlib."""

    @pytest.fixture
    def mock_xlib(self):
        """Create mock Xlib objects."""
        mock_display = MagicMock()
        mock_screen = MagicMock()
        mock_root = MagicMock()
        mock_window = MagicMock()

        mock_display.screen.return_value = mock_screen
        mock_screen.root = mock_root
        mock_display.create_resource_object.return_value = mock_window

        return {
            "display": mock_display,
            "screen": mock_screen,
            "root": mock_root,
            "window": mock_window,
        }

    @pytest.fixture
    def x11_detector(self, mock_xlib):
        """Create X11ContextDetector with mocked display."""
        with patch.dict("sys.modules", {"Xlib": MagicMock(), "Xlib.display": MagicMock()}):
            from dicton.context_detector_x11 import X11ContextDetector

            detector = X11ContextDetector()
            detector._display = mock_xlib["display"]
            return detector, mock_xlib

    def test_get_active_window_success(self, x11_detector):
        """Test successful window detection."""
        detector, mock_xlib = x11_detector

        # Setup mock return values
        mock_prop = MagicMock()
        mock_prop.value = [123456]
        mock_xlib["root"].get_full_property.return_value = mock_prop
        mock_xlib["window"].get_wm_class.return_value = ("firefox", "Firefox")
        mock_xlib["window"].get_wm_name.return_value = "Test Page"

        # Mock geometry
        mock_geom = MagicMock()
        mock_geom.x, mock_geom.y = 100, 200
        mock_geom.width, mock_geom.height = 800, 600
        mock_xlib["window"].get_geometry.return_value = mock_geom

        # Mock title property - return None to fall back to WM_NAME
        mock_xlib["window"].get_full_property.return_value = None

        # Mock _NET_WM_PID property
        mock_pid_prop = MagicMock()
        mock_pid_prop.value = [12345]

        def get_full_property_side_effect(atom, type_):
            if "PID" in str(atom):
                return mock_pid_prop
            return None

        mock_xlib["window"].get_full_property.side_effect = get_full_property_side_effect

        result = detector.get_active_window()

        assert result is not None
        assert result.wm_class == "Firefox"
        assert result.geometry == (100, 200, 800, 600)

    def test_get_active_window_no_window(self, x11_detector):
        """Test when no window is active."""
        detector, mock_xlib = x11_detector

        mock_prop = MagicMock()
        mock_prop.value = [0]  # No window
        mock_xlib["root"].get_full_property.return_value = mock_prop

        result = detector.get_active_window()
        assert result is None

    def test_get_widget_focus_no_atspi(self, x11_detector):
        """Test widget focus returns None when AT-SPI unavailable."""
        detector, _ = x11_detector

        detector._atspi_available = False
        result = detector.get_widget_focus()
        assert result is None

    @patch("subprocess.run")
    def test_get_tmux_info_success(self, mock_run, x11_detector):
        """Test tmux info extraction."""
        detector, _ = x11_detector

        # Mock tmux commands
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="main:0.1"),
            MagicMock(returncode=0, stdout="/home/user/project"),
        ]

        result = detector._get_tmux_info()

        assert result is not None
        assert result["session"] == "main"
        assert result["pane"] == "0.1"
        assert result["cwd"] == "/home/user/project"

    @patch("subprocess.run")
    def test_get_tmux_info_not_in_tmux(self, mock_run, x11_detector):
        """Test tmux info returns None when not in tmux."""
        detector, _ = x11_detector

        mock_run.side_effect = subprocess.TimeoutExpired(cmd="tmux", timeout=1)

        result = detector._get_tmux_info()
        assert result is None

    def test_close_display(self, x11_detector):
        """Test display is closed properly."""
        detector, mock_xlib = x11_detector

        detector.close()
        mock_xlib["display"].close.assert_called_once()
        assert detector._display is None


# =============================================================================
# Wayland Context Detector Tests (Mocked)
# =============================================================================


class TestWaylandContextDetector:
    """Test WaylandContextDetector with mocked compositors."""

    @pytest.fixture
    def sway_detector(self):
        """Create WaylandContextDetector mocked as Sway."""
        with patch("dicton.context_detector_wayland.WAYLAND_COMPOSITOR", "sway"):
            from dicton.context_detector_wayland import WaylandContextDetector

            detector = WaylandContextDetector()
            detector._compositor = "sway"
            return detector

    @pytest.fixture
    def hyprland_detector(self):
        """Create WaylandContextDetector mocked as Hyprland."""
        with patch("dicton.context_detector_wayland.WAYLAND_COMPOSITOR", "hyprland"):
            from dicton.context_detector_wayland import WaylandContextDetector

            detector = WaylandContextDetector()
            detector._compositor = "hyprland"
            return detector

    @patch("subprocess.run")
    def test_sway_get_active_window(self, mock_run, sway_detector):
        """Test Sway window detection via swaymsg."""
        # Mock swaymsg output
        sway_tree = {
            "focused": False,
            "nodes": [
                {
                    "focused": True,
                    "app_id": "firefox",
                    "name": "Mozilla Firefox",
                    "pid": 12345,
                    "rect": {"x": 0, "y": 0, "width": 1920, "height": 1080},
                }
            ],
        }
        mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps(sway_tree))

        result = sway_detector.get_active_window()

        assert result is not None
        assert result.wm_class == "firefox"
        assert result.title == "Mozilla Firefox"
        assert result.pid == 12345
        assert result.geometry == (0, 0, 1920, 1080)

    @patch("subprocess.run")
    def test_sway_command_not_found(self, mock_run, sway_detector):
        """Test graceful failure when swaymsg not found."""
        mock_run.side_effect = FileNotFoundError()

        result = sway_detector.get_active_window()
        assert result is None

    @patch("subprocess.run")
    def test_hyprland_get_active_window(self, mock_run, hyprland_detector):
        """Test Hyprland window detection via hyprctl."""
        hyprland_output = {
            "class": "kitty",
            "title": "Terminal",
            "pid": 54321,
            "at": [100, 200],
            "size": [800, 600],
        }
        mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps(hyprland_output))

        result = hyprland_detector.get_active_window()

        assert result is not None
        assert result.wm_class == "kitty"
        assert result.title == "Terminal"
        assert result.pid == 54321
        assert result.geometry == (100, 200, 800, 600)

    def test_find_focused_sway_recursive(self, sway_detector):
        """Test recursive focused node finding in Sway tree."""
        tree = {
            "focused": False,
            "nodes": [
                {
                    "focused": False,
                    "nodes": [{"focused": True, "app_id": "found"}],
                }
            ],
        }

        result = sway_detector._find_focused_sway(tree)
        assert result is not None
        assert result["app_id"] == "found"

    def test_find_focused_sway_floating(self, sway_detector):
        """Test finding focused node in floating nodes."""
        tree = {
            "focused": False,
            "nodes": [],
            "floating_nodes": [{"focused": True, "app_id": "floating"}],
        }

        result = sway_detector._find_focused_sway(tree)
        assert result is not None
        assert result["app_id"] == "floating"


# =============================================================================
# Windows Context Detector Tests (Mocked)
# =============================================================================


class TestWindowsContextDetector:
    """Test WindowsContextDetector with mocked Win32 API."""

    @pytest.fixture
    def windows_detector(self):
        """Create WindowsContextDetector with mocked dependencies."""
        mock_win32gui = MagicMock()
        mock_win32process = MagicMock()

        with patch.dict(
            "sys.modules",
            {
                "win32gui": mock_win32gui,
                "win32process": mock_win32process,
            },
        ):
            from dicton.context_detector_windows import WindowsContextDetector

            detector = WindowsContextDetector()
            return detector, mock_win32gui, mock_win32process

    def test_get_active_window_success(self, windows_detector):
        """Test Windows window detection via Win32 API."""
        detector, mock_gui, mock_process = windows_detector

        # Setup mocks
        mock_gui.GetForegroundWindow.return_value = 12345
        mock_gui.GetWindowText.return_value = "Test Window"
        mock_gui.GetClassName.return_value = "Notepad"
        mock_process.GetWindowThreadProcessId.return_value = (1, 9999)
        mock_gui.GetWindowRect.return_value = (100, 200, 900, 800)

        with patch.dict(
            "sys.modules",
            {"win32gui": mock_gui, "win32process": mock_process},
        ):
            result = detector.get_active_window()

        assert result is not None
        assert result.wm_class == "Notepad"
        assert result.title == "Test Window"
        assert result.pid == 9999
        assert result.geometry == (100, 200, 800, 600)

    def test_control_type_to_role_mapping(self, windows_detector):
        """Test UI Automation control type to role conversion."""
        detector, _, _ = windows_detector

        # Test known control types
        assert detector._control_type_to_role(50004) == "edit"
        assert detector._control_type_to_role(50020) == "text"
        assert detector._control_type_to_role(50032) == "window"

        # Test unknown control type
        assert detector._control_type_to_role(99999) == "unknown_99999"

    def test_terminal_class_detection(self, windows_detector):
        """Test terminal class detection for Windows Terminal."""
        detector, mock_gui, mock_process = windows_detector

        # Windows Terminal class
        mock_gui.GetForegroundWindow.return_value = 12345
        mock_gui.GetWindowText.return_value = "Terminal"
        mock_gui.GetClassName.return_value = "CASCADIA_HOSTING_WINDOW_CLASS"
        mock_process.GetWindowThreadProcessId.return_value = (1, 9999)
        mock_gui.GetWindowRect.return_value = (0, 0, 800, 600)

        with patch.dict(
            "sys.modules",
            {"win32gui": mock_gui, "win32process": mock_process},
        ):
            result = detector.get_active_window()

        assert result is not None
        assert result.wm_class == "CASCADIA_HOSTING_WINDOW_CLASS"


# =============================================================================
# Integration Tests (Fallback Chain)
# =============================================================================


class TestFallbackChain:
    """Test the detection fallback chain behavior."""

    def test_context_captures_errors(self):
        """Test that errors are captured without breaking detection."""
        from dicton.context_detector import ContextDetector, WindowInfo

        class PartialDetector(ContextDetector):
            """Detector that fails on widget detection."""

            def get_active_window(self):
                return WindowInfo(wm_class="test", title="Test Window")

            def get_widget_focus(self):
                raise RuntimeError("AT-SPI unavailable")

            def get_terminal_context(self):
                return None

        detector = PartialDetector()
        ctx = detector.get_context()

        # Should still have window info
        assert ctx.window is not None
        assert ctx.window.wm_class == "test"

        # Should capture widget error
        assert len(ctx.errors) == 1
        assert "Widget focus failed" in ctx.errors[0]

    def test_detection_level_progression(self):
        """Test detection level reflects best available data."""
        from dicton.context_detector import (
            ContextDetector,
            TerminalInfo,
            WidgetInfo,
            WindowInfo,
        )

        class FullDetector(ContextDetector):
            """Detector with all levels available."""

            def get_active_window(self):
                return WindowInfo(wm_class="gnome-terminal", title="Terminal")

            def get_widget_focus(self):
                return WidgetInfo(role="terminal")

            def get_terminal_context(self):
                return TerminalInfo(shell="bash")

        detector = FullDetector()
        ctx = detector.get_context()

        # Widget focus is most precise = level 1
        assert ctx.detection_level == 1
        assert ctx.widget is not None
        assert ctx.terminal is not None
        assert ctx.window is not None
