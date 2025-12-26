"""Selection handler for Dicton - Read X11 PRIMARY selection

This module provides access to the X11 PRIMARY selection (highlighted text)
without requiring Ctrl+C. Uses xclip for reliable cross-toolkit support.
"""

import subprocess

from .config import config
from .platform_utils import IS_LINUX


def get_primary_selection() -> str | None:
    """Get the currently selected text from X11 PRIMARY selection.

    On X11, when you highlight text with the mouse, it's automatically
    copied to the PRIMARY selection. This function reads that selection
    without disturbing the clipboard.

    Returns:
        The selected text, or None if nothing is selected or on error.
    """
    if not IS_LINUX:
        if config.DEBUG:
            print("PRIMARY selection only available on Linux/X11")
        return None

    try:
        # xclip -selection primary -o reads PRIMARY selection
        result = subprocess.run(
            ["xclip", "-selection", "primary", "-o"],
            capture_output=True,
            text=True,
            timeout=2.0,
        )

        if result.returncode == 0 and result.stdout:
            return result.stdout.strip()

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

    try:
        result = subprocess.run(
            ["xclip", "-selection", "clipboard", "-o"],
            capture_output=True,
            text=True,
            timeout=2.0,
        )

        if result.returncode == 0 and result.stdout:
            return result.stdout.strip()

        return None

    except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
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

    try:
        process = subprocess.Popen(
            ["xclip", "-selection", "clipboard"],
            stdin=subprocess.PIPE,
            text=True,
        )
        process.communicate(input=text, timeout=2.0)
        return process.returncode == 0

    except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
        return False
