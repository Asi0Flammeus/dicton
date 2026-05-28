"""Linux clipboard + paste backend."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import time
from collections.abc import Callable


def _is_wayland() -> bool:
    # Pick clipboard tools by the *session*, not by which binary happens to be
    # installed: wl-copy/wtype exit non-zero without a live Wayland socket, so
    # preferring them on an X11 session (or from a systemd user service that
    # only inherited DISPLAY/XWayland, not WAYLAND_DISPLAY) breaks paste.
    return bool(os.environ.get("WAYLAND_DISPLAY"))


def _paste_linux(text: str) -> None:
    # No clipboard restore: the focused app may still be reading the new
    # clipboard content when we send the key event, so an immediate restore
    # races and pastes the *old* content instead. Main's adapter behaves the
    # same way — the dictation simply replaces the clipboard.
    #
    # Try the session-native (copy, send) pair first, then fall back to the
    # other — covers X11, Wayland, and the mixed XWayland-from-systemd case.
    data = text.encode("utf-8")
    errors: list[str] = []
    for copy_cmd, send in _paste_strategies():
        try:
            subprocess.run(copy_cmd, input=data, check=True, capture_output=True)
        except (OSError, subprocess.CalledProcessError) as exc:
            errors.append(f"{copy_cmd[0]} ({exc})")
            continue
        time.sleep(0.02)
        send()
        return
    raise RuntimeError(
        "clipboard copy failed — tried " + ", ".join(errors)
        if errors
        else "install wl-clipboard (Wayland) or xclip (X11)"
    )


def _paste_strategies() -> list[tuple[list[str], Callable[[], None]]]:
    """Ordered (copy command, keystroke sender) pairs, session-native first."""
    wayland: list[tuple[list[str], Callable[[], None]]] = []
    x11: list[tuple[list[str], Callable[[], None]]] = []
    if shutil.which("wl-copy"):
        wayland.append((["wl-copy"], _send_keys_wayland))
    if shutil.which("xclip"):
        x11.append((["xclip", "-selection", "clipboard"], _send_keys_x11))
    return wayland + x11 if _is_wayland() else x11 + wayland


# Ctrl+Shift+V is the universal paste shortcut: it works in browsers, editors
# *and* terminals (gnome-terminal, kitty, alacritty…). Plain Ctrl+V hits
# "quoted-insert" in zsh/vim and is intercepted by tmux.
def _send_keys_wayland() -> None:
    if shutil.which("wtype"):
        subprocess.run(["wtype", "-M", "ctrl", "-M", "shift", "v"], check=False)
        return
    if shutil.which("ydotool"):
        # 29=LeftCtrl, 42=LeftShift, 47=V
        subprocess.run(
            ["ydotool", "key", "29:1", "42:1", "47:1", "47:0", "42:0", "29:0"], check=False
        )
        return
    _send_keys_x11()  # last resort: xdotool can still reach XWayland windows


def _send_keys_x11() -> None:
    if shutil.which("xdotool"):
        _log_active_window("paste target")
        subprocess.run(
            ["xdotool", "key", "--clearmodifiers", "--delay", "0", "ctrl+shift+v"],
            check=False,
        )
        return
    raise RuntimeError("install xdotool (X11) or wtype/ydotool (Wayland) to send keystrokes")


def _log_active_window(label: str) -> None:
    log = logging.getLogger("dicton")
    try:
        win = subprocess.run(
            ["xdotool", "getactivewindow", "getwindowname"],
            capture_output=True,
            text=True,
            check=False,
            timeout=1.0,
        )
        log.info("%s: active window = %r", label, win.stdout.strip())
    except Exception as exc:  # noqa: BLE001
        log.warning("could not get active window: %s", exc)
