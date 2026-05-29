"""Wizard probes — small OS-specific feature checks.

Kept here so the wizard never has to look at ``sys.platform`` itself.
"""

from __future__ import annotations

import shutil
import sys
from typing import Literal


def clipboard_tools_status() -> Literal["ok", "missing", "na"]:
    """Tri-state report on whether usable clipboard tooling is installed.

    ``"na"`` on non-Linux platforms (the wizard doesn't probe Windows /
    macOS clipboard tools — they ship in the OS). ``"ok"`` if at least
    one of wl-copy / xclip is on PATH; ``"missing"`` otherwise.
    """
    if sys.platform != "linux":
        return "na"
    if shutil.which("wl-copy") or shutil.which("xclip"):
        return "ok"
    return "missing"


def capture_primary_key_supported() -> bool:
    """Whether live evdev keycode capture is available — Linux only."""
    return sys.platform == "linux"
