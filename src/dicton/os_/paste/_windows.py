"""Windows clipboard + paste backend."""

from __future__ import annotations

import ctypes
import time
from ctypes import wintypes


def paste_windows(text: str) -> None:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    # ULONG_PTR is pointer-sized: 8 bytes on x64, 4 on x86. Without an
    # explicit argtypes/restype declaration ctypes defaults to c_int (32
    # bits) and silently truncates handles on x64 — that's why the old
    # code silently no-op'd.
    ULONG_PTR = ctypes.c_size_t  # noqa: N806

    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = wintypes.LPVOID
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalUnlock.restype = wintypes.BOOL
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.EmptyClipboard.argtypes = []
    user32.EmptyClipboard.restype = wintypes.BOOL
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user32.SetClipboardData.restype = wintypes.HANDLE
    user32.CloseClipboard.argtypes = []
    user32.CloseClipboard.restype = wintypes.BOOL

    CF_UNICODETEXT = 13  # noqa: N806
    GMEM_MOVEABLE = 0x0002  # noqa: N806

    encoded = (text + "\0").encode("utf-16-le")
    h = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(encoded))
    if not h:
        raise OSError(f"GlobalAlloc failed: {ctypes.get_last_error()}")
    locked = kernel32.GlobalLock(h)
    if not locked:
        raise OSError(f"GlobalLock failed: {ctypes.get_last_error()}")
    ctypes.memmove(locked, encoded, len(encoded))
    kernel32.GlobalUnlock(h)

    # OpenClipboard can fail if another app holds the clipboard; retry
    # briefly. Most contention resolves in a frame or two.
    opened = False
    for _ in range(10):
        if user32.OpenClipboard(None):
            opened = True
            break
        time.sleep(0.01)
    if not opened:
        raise OSError(f"OpenClipboard failed: {ctypes.get_last_error()}")
    try:
        user32.EmptyClipboard()
        if not user32.SetClipboardData(CF_UNICODETEXT, h):
            raise OSError(f"SetClipboardData failed: {ctypes.get_last_error()}")
    finally:
        user32.CloseClipboard()

    # SendInput Ctrl+V — the INPUT union must be sized to MOUSEINPUT (the
    # largest variant), otherwise sizeof(INPUT) is wrong and SendInput
    # reads garbage past our keyboard records.
    INPUT_KEYBOARD = 1  # noqa: N806
    KEYEVENTF_KEYUP = 0x0002  # noqa: N806
    VK_CONTROL = 0x11  # noqa: N806
    V_KEY = 0x56  # noqa: N806

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [
            ("dx", wintypes.LONG),
            ("dy", wintypes.LONG),
            ("mouseData", wintypes.DWORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ULONG_PTR),
        ]

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", wintypes.WORD),
            ("wScan", wintypes.WORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ULONG_PTR),
        ]

    class HARDWAREINPUT(ctypes.Structure):
        _fields_ = [
            ("uMsg", wintypes.DWORD),
            ("wParamL", wintypes.WORD),
            ("wParamH", wintypes.WORD),
        ]

    class _U(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", wintypes.DWORD), ("u", _U)]

    user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
    user32.SendInput.restype = wintypes.UINT

    def _ev(vk: int, up: bool) -> INPUT:
        inp = INPUT()
        inp.type = INPUT_KEYBOARD
        inp.u.ki = KEYBDINPUT(vk, 0, KEYEVENTF_KEYUP if up else 0, 0, 0)
        return inp

    events = (INPUT * 4)(
        _ev(VK_CONTROL, False),
        _ev(V_KEY, False),
        _ev(V_KEY, True),
        _ev(VK_CONTROL, True),
    )
    sent = user32.SendInput(4, events, ctypes.sizeof(INPUT))
    if sent != 4:
        raise OSError(f"SendInput sent {sent}/4 events: {ctypes.get_last_error()}")
