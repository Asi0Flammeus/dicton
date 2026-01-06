"""Platform detection and cross-platform utilities for Dicton"""

import os
import platform
import sys
from enum import Enum

# =============================================================================
# Platform Detection
# =============================================================================

IS_WINDOWS = sys.platform == "win32"
IS_LINUX = sys.platform.startswith("linux")
IS_MACOS = sys.platform == "darwin"

# Display system detection (Linux-specific)
IS_X11 = False
IS_WAYLAND = False
WAYLAND_COMPOSITOR: str | None = None

if IS_LINUX:
    session_type = os.environ.get("XDG_SESSION_TYPE", "").lower()
    IS_X11 = session_type == "x11" or os.environ.get("DISPLAY") is not None
    IS_WAYLAND = session_type == "wayland"

    # Detect specific Wayland compositor for context detection strategy
    if IS_WAYLAND:
        desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
        if "gnome" in desktop:
            WAYLAND_COMPOSITOR = "gnome"
        elif "kde" in desktop or "plasma" in desktop:
            WAYLAND_COMPOSITOR = "kde"
        elif os.environ.get("SWAYSOCK"):
            WAYLAND_COMPOSITOR = "sway"
        elif os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
            WAYLAND_COMPOSITOR = "hyprland"
        else:
            WAYLAND_COMPOSITOR = "unknown"


class DisplayServer(Enum):
    """Display server types for Linux systems."""

    X11 = "x11"
    WAYLAND = "wayland"
    UNKNOWN = "unknown"


class Platform(Enum):
    """Operating system platforms."""

    LINUX = "linux"
    WINDOWS = "windows"
    MACOS = "macos"
    UNKNOWN = "unknown"


def get_platform() -> Platform:
    """Get the current operating system platform."""
    if IS_WINDOWS:
        return Platform.WINDOWS
    elif IS_LINUX:
        return Platform.LINUX
    elif IS_MACOS:
        return Platform.MACOS
    return Platform.UNKNOWN


def get_display_server() -> DisplayServer:
    """Get the current display server (Linux only)."""
    if not IS_LINUX:
        return DisplayServer.UNKNOWN
    if IS_X11:
        return DisplayServer.X11
    if IS_WAYLAND:
        return DisplayServer.WAYLAND
    return DisplayServer.UNKNOWN


def get_wayland_compositor() -> str | None:
    """Get the Wayland compositor name (Linux Wayland only).

    Returns:
        Compositor name: "gnome", "kde", "sway", "hyprland", "unknown"
        None if not running on Wayland
    """
    if not IS_WAYLAND:
        return None
    return WAYLAND_COMPOSITOR


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
        "wayland_compositor": WAYLAND_COMPOSITOR,
        "platform": get_platform().value,
        "display_server": get_display_server().value,
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
            print(f"Display: Wayland ({info['wayland_compositor']})")
        else:
            print("Display: Unknown")
