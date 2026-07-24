"""Selection handler for Dicton - Read PRIMARY selection

This module provides access to the PRIMARY selection (highlighted text)
without requiring Ctrl+C. Supports both X11 (xclip) and Wayland (wl-paste).
"""

import os
import subprocess

from .config import config
from .platform_utils import IS_LINUX, IS_WAYLAND, IS_X11


def get_primary_selection() -> str | None:
    """Get the currently selected text from PRIMARY selection.

    On X11, when you highlight text with the mouse, it's automatically
    copied to the PRIMARY selection. On Wayland, uses wl-paste.

    Returns:
        The selected text, or None if nothing is selected or on error.
    """
    if not IS_LINUX:
        if config.DEBUG:
            print("PRIMARY selection only available on Linux")
        return None

    # Try Wayland first if detected
    if IS_WAYLAND:
        result = _get_selection_wayland()
        if result is not None:
            return result
        # Fall through to X11 in case of XWayland

    # X11 works natively on X11 and through XWayland when DISPLAY is available.
    if IS_X11 or not IS_WAYLAND or os.environ.get("DISPLAY"):
        return _get_selection_x11()

    return None


def _get_selection_wayland() -> str | None:
    """Get selection using wl-paste (Wayland)."""
    try:
        # wl-paste -p reads PRIMARY selection
        result = subprocess.run(
            ["wl-paste", "-p", "-n"],  # -p = primary, -n = no newline
            capture_output=True,
            text=True,
            timeout=2.0,
        )

        if result.returncode == 0 and result.stdout:
            return result.stdout

        return None

    except FileNotFoundError:
        if config.DEBUG:
            print("wl-paste not found. Install with: sudo apt install wl-clipboard")
        return None
    except subprocess.TimeoutExpired:
        if config.DEBUG:
            print("wl-paste timed out")
        return None
    except Exception as e:
        if config.DEBUG:
            print(f"wl-paste error: {e}")
        return None


def _get_selection_x11() -> str | None:
    """Get selection using xclip (X11)."""
    try:
        # xclip -selection primary -o reads PRIMARY selection
        result = subprocess.run(
            ["xclip", "-selection", "primary", "-o"],
            capture_output=True,
            text=True,
            timeout=2.0,
        )

        if result.returncode == 0 and result.stdout:
            return result.stdout

        return None

    except FileNotFoundError:
        if config.DEBUG:
            print("xclip not installed. Install with: sudo apt install xclip")
        return None
    except subprocess.TimeoutExpired:
        if config.DEBUG:
            print("xclip timed out reading selection")
        return None
    except Exception as e:
        if config.DEBUG:
            print(f"Error reading selection: {e}")
        return None


def has_selection() -> bool:
    """Check if there is any text currently selected.

    Returns:
        True if text is selected, False otherwise.
    """
    selection = get_primary_selection()
    return selection is not None and len(selection) > 0


def get_clipboard() -> str | None:
    """Get text from the system clipboard (CLIPBOARD selection).

    This is the standard Ctrl+C clipboard, not the PRIMARY selection.

    Returns:
        The clipboard text, or None if empty or on error.
    """
    if not IS_LINUX:
        return None

    if IS_WAYLAND:
        try:
            result = subprocess.run(
                ["wl-paste", "-n"],
                capture_output=True,
                text=True,
                timeout=2.0,
            )
            if result.returncode == 0 and result.stdout:
                return result.stdout
        except Exception:
            pass

        if not os.environ.get("DISPLAY"):
            return None

    try:
        result = subprocess.run(
            ["xclip", "-selection", "clipboard", "-o"],
            capture_output=True,
            text=True,
            timeout=2.0,
        )

        if result.returncode == 0 and result.stdout:
            return result.stdout

        return None

    except Exception:
        return None


def set_clipboard(text: str) -> bool:
    """Set text to the system clipboard.

    Args:
        text: Text to copy to clipboard.

    Returns:
        True if successful, False otherwise.
    """
    if not IS_LINUX or not text:
        return False

    if IS_WAYLAND:
        try:
            result = subprocess.run(
                ["wl-copy"],
                input=text,
                capture_output=True,
                text=True,
                timeout=2.0,
            )
            if result.returncode == 0:
                return True
        except Exception:
            pass

        if not os.environ.get("DISPLAY"):
            return False

    try:
        process = subprocess.Popen(
            ["xclip", "-selection", "clipboard"],
            stdin=subprocess.PIPE,
            text=True,
        )
        process.communicate(input=text, timeout=2.0)
        return process.returncode == 0

    except Exception:
        return False
