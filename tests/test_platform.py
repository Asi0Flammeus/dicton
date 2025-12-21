"""Tests for Dicton platform detection module."""

import sys

import pytest


class TestPlatformConstants:
    """Test platform detection constants."""

    def test_platform_flags_mutually_exclusive(self):
        """Test only one platform flag is True at a time."""
        from dicton.platform_utils import IS_LINUX, IS_MACOS, IS_WINDOWS

        # Exactly one should be True (or all False if unknown platform)
        true_count = sum([IS_WINDOWS, IS_LINUX, IS_MACOS])
        assert true_count <= 1, "Multiple platform flags are True"

    def test_current_platform_detected(self):
        """Test current platform is detected correctly."""
        from dicton.platform_utils import IS_LINUX, IS_MACOS, IS_WINDOWS

        if sys.platform == "win32":
            assert IS_WINDOWS is True
        elif sys.platform.startswith("linux"):
            assert IS_LINUX is True
        elif sys.platform == "darwin":
            assert IS_MACOS is True


class TestGetPlatformInfo:
    """Test get_platform_info function."""

    def test_returns_dict(self):
        """Test get_platform_info returns a dictionary."""
        from dicton.platform_utils import get_platform_info

        info = get_platform_info()
        assert isinstance(info, dict)

    def test_contains_required_keys(self):
        """Test returned dict contains all required keys."""
        from dicton.platform_utils import get_platform_info

        info = get_platform_info()
        required_keys = [
            "system",
            "release",
            "version",
            "machine",
            "python_version",
            "is_windows",
            "is_linux",
            "is_macos",
            "is_x11",
            "is_wayland",
        ]
        for key in required_keys:
            assert key in info, f"Missing key: {key}"

    def test_platform_flags_are_booleans(self):
        """Test platform flags in info dict are booleans."""
        from dicton.platform_utils import get_platform_info

        info = get_platform_info()
        bool_keys = ["is_windows", "is_linux", "is_macos", "is_x11", "is_wayland"]
        for key in bool_keys:
            assert isinstance(info[key], bool), f"{key} is not a boolean"

    def test_string_values_not_empty(self):
        """Test string values are not empty."""
        from dicton.platform_utils import get_platform_info

        info = get_platform_info()
        string_keys = ["system", "machine", "python_version"]
        for key in string_keys:
            assert isinstance(info[key], str), f"{key} is not a string"
            assert len(info[key]) > 0, f"{key} is empty"


class TestLinuxDisplayDetection:
    """Test Linux display system detection (X11/Wayland)."""

    @pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux only")
    def test_display_detection_on_linux(self):
        """Test display system is detected on Linux."""
        from dicton.platform_utils import IS_LINUX, IS_WAYLAND, IS_X11

        if IS_LINUX:
            # At least one should be detected, or both False if headless
            # This is informational - just verify the flags exist
            assert isinstance(IS_X11, bool)
            assert isinstance(IS_WAYLAND, bool)

    @pytest.mark.skipif(sys.platform.startswith("linux"), reason="Non-Linux only")
    def test_display_detection_on_non_linux(self):
        """Test display flags are False on non-Linux."""
        from dicton.platform_utils import IS_WAYLAND, IS_X11

        assert IS_X11 is False
        assert IS_WAYLAND is False


class TestPrintPlatformInfo:
    """Test print_platform_info function."""

    def test_prints_without_error(self, capsys):
        """Test print_platform_info runs without error."""
        from dicton.platform_utils import print_platform_info

        # Should not raise
        print_platform_info()

        captured = capsys.readouterr()
        assert "Platform:" in captured.out
        assert "Python:" in captured.out
