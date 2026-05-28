"""macOS clipboard + paste backend."""

from __future__ import annotations

import subprocess
import time


def paste_darwin(text: str) -> None:
    subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True)
    time.sleep(0.02)
    subprocess.run(
        [
            "osascript",
            "-e",
            'tell application "System Events" to keystroke "v" using command down',
        ],
        check=False,
    )
