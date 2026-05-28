"""OS-specific wizard probes."""

from __future__ import annotations

import shutil
import sys
from typing import Literal


def clipboard_tools_status() -> Literal["ok", "missing", "na"]:
    if sys.platform != "linux":
        return "na"
    missing = [c for c in ("wl-copy", "xclip") if not shutil.which(c)]
    return "missing" if len(missing) == 2 else "ok"


def capture_primary_key_supported() -> bool:
    return sys.platform == "linux"
