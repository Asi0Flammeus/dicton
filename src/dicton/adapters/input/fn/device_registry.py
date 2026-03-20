"""Low-level keyboard device discovery helpers."""

from __future__ import annotations

from .parser import KEY_WAKEUP


def _is_external_keyboard(name: str) -> bool:
    external_brands = ["ZSA", "Voyager", "Ergodox", "Moonlander", "Planck"]
    return any(brand.lower() in name.lower() for brand in external_brands)


def _open_all_devices(*, debug: bool = False) -> list:
    """Open all available input devices, skipping any that fail.

    Resilient to transient failures during device hotplug: if a device node
    exists but cannot be opened (e.g., being added/removed), it is silently
    skipped instead of aborting the entire discovery.
    """
    import evdev

    devices = []
    for path in evdev.list_devices():
        try:
            devices.append(evdev.InputDevice(path))
        except (OSError, PermissionError) as exc:
            if debug:
                print(f"  Skipping {path}: {exc}")
    return devices


def find_keyboard_devices(
    *,
    custom_hotkey_enabled: bool,
    custom_hotkey_keycode: int | None,
    secondary_hotkeys: dict[int, object],
    debug: bool = False,
):
    """Find primary and secondary keyboard devices for FN/custom hotkeys."""
    try:
        import evdev  # noqa: F401
        from evdev import ecodes

        devices = _open_all_devices(debug=debug)

        if debug:
            print("Scanning input devices...")
            for device in devices:
                caps = device.capabilities()
                if ecodes.EV_KEY in caps:
                    keys = caps[ecodes.EV_KEY]
                    has_wakeup = KEY_WAKEUP in keys
                    is_ext = _is_external_keyboard(device.name)
                    if has_wakeup or is_ext:
                        print(
                            f"  {device.path}: {device.name} (WAKEUP={has_wakeup}, external={is_ext})"
                        )

        primary_device = None
        secondary_devices = []

        if custom_hotkey_enabled and custom_hotkey_keycode:
            for device in devices:
                if _is_external_keyboard(device.name):
                    continue
                caps = device.capabilities()
                if ecodes.EV_KEY in caps:
                    keys = caps[ecodes.EV_KEY]
                    if custom_hotkey_keycode in keys and ecodes.KEY_A in keys:
                        if debug:
                            print(f"Found keyboard for custom hotkey: {device.name}")
                        primary_device = device
                        break

        if not primary_device:
            for device in devices:
                if _is_external_keyboard(device.name):
                    continue
                caps = device.capabilities()
                if ecodes.EV_KEY in caps:
                    keys = caps[ecodes.EV_KEY]
                    if KEY_WAKEUP in keys or 464 in keys:
                        primary_device = device
                        break

        if secondary_hotkeys:
            for device in devices:
                if device == primary_device:
                    continue
                caps = device.capabilities()
                if ecodes.EV_KEY in caps:
                    keys = caps[ecodes.EV_KEY]
                    has_secondary = any(keycode in keys for keycode in secondary_hotkeys)
                    if has_secondary and ecodes.KEY_A in keys:
                        secondary_devices.append(device)

        if not primary_device:
            for device in devices:
                if _is_external_keyboard(device.name):
                    continue
                caps = device.capabilities()
                if ecodes.EV_KEY in caps:
                    keys = caps[ecodes.EV_KEY]
                    if ecodes.KEY_A in keys and ecodes.KEY_Z in keys:
                        if debug:
                            print(f"Using fallback laptop keyboard: {device.name}")
                        primary_device = device
                        break

        return primary_device, secondary_devices
    except PermissionError:
        print("Permission denied accessing input devices")
        print("Add user to 'input' group: sudo usermod -aG input $USER")
        return None, []
    except Exception as exc:
        if debug:
            print(f"Error finding keyboard device: {exc}")
        return None, []


def build_device_fd_map(primary_device, secondary_devices) -> dict:
    """Build a file-descriptor map for the listener loop."""
    devices = {}
    if primary_device:
        devices[primary_device.fd] = primary_device
    for sec_device in secondary_devices:
        devices[sec_device.fd] = sec_device
    return devices
