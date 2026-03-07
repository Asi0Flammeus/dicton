"""Pure parsing helpers for FN and custom hotkey configuration."""

from __future__ import annotations

from dataclasses import dataclass

from ....processing_mode import ProcessingMode

# XF86WakeUp keycode - typically mapped to FN key on many laptops
KEY_WAKEUP = 143

# Modifier keycodes (from evdev/ecodes)
KEY_SPACE = 57
KEY_LEFTCTRL = 29
KEY_RIGHTCTRL = 97
KEY_LEFTSHIFT = 42
KEY_RIGHTSHIFT = 54
KEY_LEFTALT = 56
KEY_RIGHTALT = 100

SECONDARY_HOTKEY_MAP = {
    "escape": 1,
    "esc": 1,
    "f1": 59,
    "f2": 60,
    "f3": 61,
    "f4": 62,
    "f5": 63,
    "f6": 64,
    "f7": 65,
    "f8": 66,
    "f9": 67,
    "f10": 68,
    "f11": 87,
    "f12": 88,
    "capslock": 58,
    "caps": 58,
    "pause": 119,
    "break": 119,
    "insert": 110,
    "ins": 110,
    "home": 102,
    "end": 107,
    "pageup": 104,
    "pgup": 104,
    "pagedown": 109,
    "pgdn": 109,
}

KEY_NAME_MAP = {
    "a": 30,
    "b": 48,
    "c": 46,
    "d": 32,
    "e": 18,
    "f": 33,
    "g": 34,
    "h": 35,
    "i": 23,
    "j": 36,
    "k": 37,
    "l": 38,
    "m": 50,
    "n": 49,
    "o": 24,
    "p": 25,
    "q": 16,
    "r": 19,
    "s": 31,
    "t": 20,
    "u": 22,
    "v": 47,
    "w": 17,
    "x": 45,
    "y": 21,
    "z": 44,
    "0": 11,
    "1": 2,
    "2": 3,
    "3": 4,
    "4": 5,
    "5": 6,
    "6": 7,
    "7": 8,
    "8": 9,
    "9": 10,
    "escape": 1,
    "esc": 1,
    "f1": 59,
    "f2": 60,
    "f3": 61,
    "f4": 62,
    "f5": 63,
    "f6": 64,
    "f7": 65,
    "f8": 66,
    "f9": 67,
    "f10": 68,
    "f11": 87,
    "f12": 88,
    "capslock": 58,
    "caps": 58,
    "tab": 15,
    "space": 57,
    "enter": 28,
    "return": 28,
    "backspace": 14,
    "delete": 111,
    "del": 111,
    "insert": 110,
    "ins": 110,
    "home": 102,
    "end": 107,
    "pageup": 104,
    "pgup": 104,
    "pagedown": 109,
    "pgdn": 109,
    "up": 103,
    "down": 108,
    "left": 105,
    "right": 106,
    "pause": 119,
    "break": 119,
    "grave": 41,
    "`": 41,
    "minus": 12,
    "-": 12,
    "equal": 13,
    "=": 13,
    "bracketleft": 26,
    "[": 26,
    "bracketright": 27,
    "]": 27,
    "backslash": 43,
    "\\": 43,
    "semicolon": 39,
    ";": 39,
    "apostrophe": 40,
    "'": 40,
    "comma": 51,
    ",": 51,
    "period": 52,
    ".": 52,
    "slash": 53,
    "/": 53,
}


@dataclass(frozen=True)
class CustomHotkeySpec:
    enabled: bool
    keycode: int | None = None
    requires_ctrl: bool = False
    requires_shift: bool = False
    requires_alt: bool = False


def build_secondary_hotkeys(
    *,
    secondary_hotkey: str,
    secondary_hotkey_translation: str,
    secondary_hotkey_act_on_text: str,
    advanced_modes_enabled: bool,
) -> dict[int, ProcessingMode]:
    hotkeys: dict[int, ProcessingMode] = {}

    keycode = SECONDARY_HOTKEY_MAP.get(secondary_hotkey)
    if keycode:
        hotkeys[keycode] = ProcessingMode.BASIC

    keycode = SECONDARY_HOTKEY_MAP.get(secondary_hotkey_translation)
    if keycode:
        hotkeys[keycode] = ProcessingMode.TRANSLATION

    if advanced_modes_enabled:
        keycode = SECONDARY_HOTKEY_MAP.get(secondary_hotkey_act_on_text)
        if keycode:
            hotkeys[keycode] = ProcessingMode.ACT_ON_TEXT

    return hotkeys


def parse_custom_hotkey(
    *,
    hotkey_base: str,
    hotkey_value: str,
    logger=print,
) -> CustomHotkeySpec:
    if hotkey_base == "fn":
        return CustomHotkeySpec(enabled=False)

    normalized = hotkey_value.lower().strip()
    if not normalized:
        return CustomHotkeySpec(enabled=False)

    parts = [part.strip() for part in normalized.split("+")]
    if not parts:
        return CustomHotkeySpec(enabled=False)

    main_key = parts[-1]
    modifiers = parts[:-1]

    keycode = KEY_NAME_MAP.get(main_key)
    if keycode is None:
        logger(f"⚠ Unknown key in custom hotkey: '{main_key}'")
        return CustomHotkeySpec(enabled=False)

    requires_ctrl = False
    requires_shift = False
    requires_alt = False

    for mod in modifiers:
        if mod in ("ctrl", "control"):
            requires_ctrl = True
        elif mod == "shift":
            requires_shift = True
        elif mod == "alt":
            requires_alt = True
        else:
            logger(f"⚠ Unknown modifier in custom hotkey: '{mod}'")

    return CustomHotkeySpec(
        enabled=True,
        keycode=keycode,
        requires_ctrl=requires_ctrl,
        requires_shift=requires_shift,
        requires_alt=requires_alt,
    )


def secondary_hotkey_name(keycode: int) -> str:
    for name, value in SECONDARY_HOTKEY_MAP.items():
        if value == keycode:
            return name
    return str(keycode)
