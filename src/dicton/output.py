"""Paste text into the active application."""

from __future__ import annotations

import shutil
import subprocess
import sys


def paste(text: str) -> None:
    if not text:
        return
    if sys.platform == "darwin":
        _pipe(["pbcopy"], text)
        subprocess.run(
            [
                "osascript",
                "-e",
                'tell application "System Events" to keystroke "v" using command down',
            ],
            check=False,
        )
    elif sys.platform.startswith("win"):
        _pipe(["clip"], text)
        subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "$wshell=New-Object -ComObject wscript.shell; $wshell.SendKeys('^v')",
            ],
            check=False,
        )
    else:
        if shutil.which("wl-copy"):
            _pipe(["wl-copy"], text)
            subprocess.run(["ydotool", "key", "ctrl+v"], check=False)
        elif shutil.which("xclip"):
            _pipe(["xclip", "-selection", "clipboard"], text)
            subprocess.run(["xdotool", "key", "ctrl+v"], check=False)
        else:
            raise RuntimeError("Install wl-copy+ydotool (Wayland) or xclip+xdotool (X11)")


def _pipe(cmd: list[str], text: str) -> None:
    subprocess.run(cmd, input=text.encode(), check=True)
