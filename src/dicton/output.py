"""Cross-platform clipboard + paste.

Linux: prefers wl-copy + wtype on Wayland, falls back to xclip + xdotool on
X11. macOS: pbcopy + AppleScript Cmd+V. Windows: SetClipboardData via the
`clip` command, then SendInput Ctrl+V via ctypes.

Restores the prior clipboard content after pasting.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import time


def paste(text: str) -> None:
    """Place text on the clipboard and synthesise the paste keystroke."""
    if not text:
        return
    if sys.platform == "linux":
        _paste_linux(text)
    elif sys.platform == "darwin":
        _paste_darwin(text)
    elif sys.platform == "win32":
        _paste_windows(text)
    else:
        raise RuntimeError(f"unsupported platform: {sys.platform}")


def _paste_linux(text: str) -> None:
    if shutil.which("wl-copy"):
        prior = _try_run(["wl-paste"])
        subprocess.run(["wl-copy"], input=text.encode("utf-8"), check=True)
        time.sleep(0.02)
        _send_keys_linux()
        if prior is not None:
            subprocess.run(["wl-copy"], input=prior.encode("utf-8"), check=False)
        return
    if shutil.which("xclip"):
        prior = _try_run(["xclip", "-selection", "clipboard", "-o"])
        subprocess.run(
            ["xclip", "-selection", "clipboard"],
            input=text.encode("utf-8"),
            check=True,
        )
        time.sleep(0.02)
        _send_keys_linux()
        if prior is not None:
            subprocess.run(
                ["xclip", "-selection", "clipboard"],
                input=prior.encode("utf-8"),
                check=False,
            )
        return
    raise RuntimeError("install wl-clipboard (Wayland) or xclip+xdotool (X11)")


def _send_keys_linux() -> None:
    if shutil.which("wtype"):
        subprocess.run(["wtype", "-M", "ctrl", "v"], check=False)
        return
    if shutil.which("ydotool"):
        subprocess.run(["ydotool", "key", "29:1", "47:1", "47:0", "29:0"], check=False)
        return
    if shutil.which("xdotool"):
        subprocess.run(["xdotool", "key", "--clearmodifiers", "ctrl+v"], check=False)
        return
    raise RuntimeError("install wtype (Wayland) or xdotool (X11) to send keystrokes")


def _paste_darwin(text: str) -> None:
    prior = _try_run(["pbpaste"])
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
    if prior is not None:
        subprocess.run(["pbcopy"], input=prior.encode("utf-8"), check=False)


def _paste_windows(text: str) -> None:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    CF_UNICODETEXT = 13
    GMEM_MOVEABLE = 0x0002

    encoded = (text + "\0").encode("utf-16-le")
    h = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(encoded))
    locked = kernel32.GlobalLock(h)
    ctypes.memmove(locked, encoded, len(encoded))
    kernel32.GlobalUnlock(h)

    user32.OpenClipboard(0)
    user32.EmptyClipboard()
    user32.SetClipboardData(CF_UNICODETEXT, h)
    user32.CloseClipboard()

    # SendInput Ctrl+V
    INPUT_KEYBOARD = 1
    KEYEVENTF_KEYUP = 0x0002
    VK_CONTROL = 0x11
    V_KEY = 0x56

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", wintypes.WORD),
            ("wScan", wintypes.WORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG)),
        ]

    class INPUT_I(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT)]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", wintypes.DWORD), ("i", INPUT_I)]

    def _ev(vk: int, up: bool) -> INPUT:  # type: ignore[name-defined]
        ki = KEYBDINPUT(vk, 0, KEYEVENTF_KEYUP if up else 0, 0, None)
        return INPUT(INPUT_KEYBOARD, INPUT_I(ki))

    events = (INPUT * 4)(
        _ev(VK_CONTROL, False),
        _ev(V_KEY, False),
        _ev(V_KEY, True),
        _ev(VK_CONTROL, True),
    )
    user32.SendInput(4, ctypes.byref(events), ctypes.sizeof(INPUT))


def _try_run(cmd: list[str]) -> str | None:
    try:
        r = subprocess.run(cmd, capture_output=True, check=False)
        if r.returncode != 0:
            return None
        return r.stdout.decode("utf-8", errors="replace")
    except (OSError, FileNotFoundError):
        return None
