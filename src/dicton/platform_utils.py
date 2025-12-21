"""Platform detection and cross-platform utilities for Dicton"""

import platform
import sys

# Platform detection
IS_WINDOWS = sys.platform == "win32"
IS_LINUX = sys.platform.startswith("linux")
IS_MACOS = sys.platform == "darwin"

# Display system detection (Linux-specific)
IS_X11 = False
IS_WAYLAND = False

if IS_LINUX:
    import os

    session_type = os.environ.get("XDG_SESSION_TYPE", "").lower()
    IS_X11 = session_type == "x11" or os.environ.get("DISPLAY") is not None
    IS_WAYLAND = session_type == "wayland"


def get_platform_info() -> dict:
    """Get detailed platform information."""
    return {
        "system": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "machine": platform.machine(),
        "python_version": platform.python_version(),
        "is_windows": IS_WINDOWS,
        "is_linux": IS_LINUX,
        "is_macos": IS_MACOS,
        "is_x11": IS_X11,
        "is_wayland": IS_WAYLAND,
    }


def print_platform_info():
    """Print platform information for debugging."""
    info = get_platform_info()
    print(f"Platform: {info['system']} {info['release']}")
    print(f"Python: {info['python_version']}")
    if IS_LINUX:
        if IS_X11:
            print("Display: X11")
        elif IS_WAYLAND:
            print("Display: Wayland")
        else:
            print("Display: Unknown")
