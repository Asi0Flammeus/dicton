"""FN Key Handler for Dicton - Capture XF86WakeUp (keycode 151) via evdev

This module provides FN key capture on Linux using evdev, which can detect
special keys like XF86WakeUp that pynput may not support directly.

Double-tap toggle mode:
    First tap is ignored. A second tap within the double-tap window
    starts recording. A third tap stops it.
    Advanced modes (FN+modifier) and secondary hotkeys start recording
    immediately on first press (toggle behavior).
"""

import os
import queue
import threading
import time
from collections.abc import Callable

from ....shared.config import config
from ....shared.platform_utils import IS_LINUX
from ....shared.processing_mode import ProcessingMode, advanced_modes_enabled
from .device_registry import build_device_fd_map, find_keyboard_devices
from .parser import (
    KEY_LEFTALT,
    KEY_LEFTCTRL,
    KEY_LEFTSHIFT,
    KEY_RIGHTALT,
    KEY_RIGHTCTRL,
    KEY_RIGHTSHIFT,
    KEY_SPACE,
    KEY_WAKEUP,
    build_secondary_hotkeys,
    parse_custom_hotkey,
    secondary_hotkey_name,
)
from .state_machine import HotkeyState


class FnKeyHandler:
    """Handle FN key (XF86WakeUp) with double-tap toggle mode.

    State Machine:
        IDLE + key_down (BASIC) → TAP_DOWN
        IDLE + key_down (advanced/secondary) → RECORDING_TOGGLE (immediate)
        TAP_DOWN + key_up → WAITING_DOUBLE (start double-tap timer)
        WAITING_DOUBLE + key_down (within window) → RECORDING_TOGGLE (start recording)
        WAITING_DOUBLE + timeout → IDLE (no action)
        RECORDING_TOGGLE + key_down → IDLE (stop recording, process)
    """

    def __init__(
        self,
        on_start_recording: Callable[[ProcessingMode], None] | None = None,
        on_stop_recording: Callable[[], None] | None = None,
        on_cancel_recording: Callable[[], None] | None = None,
    ):
        """Initialize FN key handler.

        Args:
            on_start_recording: Callback when recording starts, receives the ProcessingMode.
            on_stop_recording: Callback when recording stops (will process audio).
            on_cancel_recording: Callback when recording is cancelled (tap detected, discard audio).
        """
        self.on_start_recording = on_start_recording
        self.on_stop_recording = on_stop_recording
        self.on_cancel_recording = on_cancel_recording

        # State machine
        self._state = HotkeyState.IDLE
        self._state_lock = threading.Lock()

        # Current processing mode (determined by modifiers at key press)
        self._current_mode = ProcessingMode.BASIC

        # Modifier key states (tracked via evdev)
        self._space_pressed = False
        self._ctrl_pressed = False
        self._shift_pressed = False
        self._alt_pressed = False

        # Timing
        self._key_down_time: float = 0
        self._key_up_time: float = 0

        # Track if toggle mode was just started (to ignore first release for advanced modes)
        self._toggle_first_release: bool = False

        # Thresholds from config
        self._double_tap_window = config.HOTKEY_DOUBLE_TAP_WINDOW_MS / 1000.0

        # Threads
        self._listener_thread: threading.Thread | None = None
        self._timer_thread: threading.Thread | None = None
        self._running = False

        # Deliver start/stop/cancel callbacks in-order on a dedicated worker.
        self._callback_queue: queue.Queue[tuple[str, ProcessingMode | None] | None] = queue.Queue()
        self._callback_thread: threading.Thread | None = None
        self._start_callback_worker()

        # evdev devices
        self._device = None  # Primary device (laptop keyboard for FN key)
        self._secondary_devices = []  # All keyboards for secondary hotkey
        self._evdev_available = False

        # Device hot-plug support
        self._devices_lock = threading.Lock()  # Protects device list access
        self._wake_pipe_r: int | None = None  # Read end of self-pipe
        self._wake_pipe_w: int | None = None  # Write end of self-pipe
        self._device_monitor_thread: threading.Thread | None = None
        self._pyudev_available = False
        self._pending_refresh = threading.Event()  # Thread-safe flag for device refresh
        self._last_refresh_time: float = 0  # For debouncing rapid events
        self._refresh_debounce_ms = 500  # Debounce window in milliseconds

        # Secondary hotkeys: mapping of keycode → ProcessingMode
        # Each secondary hotkey triggers a specific mode directly (ignores modifier keys)
        self._secondary_hotkeys: dict[int, ProcessingMode] = {}
        self._build_secondary_hotkeys_map()

        # Track if current recording was started via secondary hotkey (mode is locked)
        self._secondary_hotkey_active = False

        # Custom hotkey support (e.g., "alt+g", "ctrl+shift+d")
        # Parsed into: required modifiers + main key
        self._custom_hotkey_enabled = False
        self._custom_hotkey_keycode: int | None = None
        self._custom_hotkey_requires_ctrl = False
        self._custom_hotkey_requires_shift = False
        self._custom_hotkey_requires_alt = False
        self._parse_custom_hotkey()

    def _build_secondary_hotkeys_map(self):
        """Build mapping of secondary hotkey keycodes to their processing modes."""
        if config.DEBUG:
            print(
                f"Secondary hotkey config: basic={config.SECONDARY_HOTKEY}, translation={config.SECONDARY_HOTKEY_TRANSLATION}, act={config.SECONDARY_HOTKEY_ACT_ON_TEXT}"
            )
        self._secondary_hotkeys = build_secondary_hotkeys(
            secondary_hotkey=config.SECONDARY_HOTKEY,
            secondary_hotkey_translation=config.SECONDARY_HOTKEY_TRANSLATION,
            secondary_hotkey_act_on_text=config.SECONDARY_HOTKEY_ACT_ON_TEXT,
            advanced_modes_enabled=advanced_modes_enabled(),
        )

    def _parse_custom_hotkey(self):
        """Parse CUSTOM_HOTKEY_VALUE into required modifiers and main key.

        Format: modifier+modifier+key (e.g., "alt+g", "ctrl+shift+d")
        Supported modifiers: ctrl, shift, alt
        """
        spec = parse_custom_hotkey(
            hotkey_base=config.HOTKEY_BASE.lower(),
            hotkey_value=config.CUSTOM_HOTKEY_VALUE,
            logger=print,
        )
        self._custom_hotkey_enabled = spec.enabled
        self._custom_hotkey_keycode = spec.keycode
        self._custom_hotkey_requires_ctrl = spec.requires_ctrl
        self._custom_hotkey_requires_shift = spec.requires_shift
        self._custom_hotkey_requires_alt = spec.requires_alt

        if config.DEBUG:
            print(
                "Custom hotkey parsed: "
                f"key={self._custom_hotkey_keycode}, "
                f"ctrl={self._custom_hotkey_requires_ctrl}, "
                f"shift={self._custom_hotkey_requires_shift}, "
                f"alt={self._custom_hotkey_requires_alt}"
            )

    def _is_custom_hotkey_modifiers_pressed(self) -> bool:
        """Check if the required modifiers for custom hotkey are currently pressed."""
        if self._custom_hotkey_requires_ctrl and not self._ctrl_pressed:
            return False
        if self._custom_hotkey_requires_shift and not self._shift_pressed:
            return False
        if self._custom_hotkey_requires_alt and not self._alt_pressed:
            return False
        return True

    def start(self):
        """Start the FN key listener"""
        if not IS_LINUX:
            print("FN key handler only supported on Linux")
            return False

        try:
            import evdev  # noqa: F401

            self._evdev_available = True
        except ImportError:
            print("evdev not installed. Install with: pip install evdev")
            print("Or: pip install dicton[fnkey]")
            return False

        # Check for pyudev (optional, for hot-plug support)
        try:
            import pyudev  # noqa: F401

            self._pyudev_available = True
        except ImportError:
            self._pyudev_available = False
            print(
                "WARNING: pyudev not installed - keyboard hot-plug detection disabled. "
                "Install with: pip install pyudev"
            )

        # Create self-pipe for waking select() on device changes
        self._wake_pipe_r, self._wake_pipe_w = os.pipe()
        os.set_blocking(self._wake_pipe_r, False)
        os.set_blocking(self._wake_pipe_w, False)

        # Find keyboard devices
        self._device, self._secondary_devices = self._find_keyboard_devices()
        if not self._device and not self._secondary_devices:
            print("No keyboard device found")
            print("You may need to run with sudo or add user to 'input' group")
            self._close_wake_pipe()
            return False

        self._running = True

        # Start device monitor for hot-plug detection
        if self._pyudev_available:
            self._device_monitor_thread = threading.Thread(
                target=self._device_monitor_loop, daemon=True
            )
            self._device_monitor_thread.start()

        self._listener_thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._listener_thread.start()

        # Log devices and configuration
        if self._custom_hotkey_enabled:
            # Custom hotkey mode (e.g., alt+g)
            print(f"Custom hotkey enabled: {config.CUSTOM_HOTKEY_VALUE}")
            if self._device:
                print(f"Listening on device: {self._device.name}")
        elif self._device:
            print(f"FN key handler started on device: {self._device.name}")

        if self._secondary_hotkeys:
            for keycode, mode in self._secondary_hotkeys.items():
                # Find the key name from the keycode
                key_name = secondary_hotkey_name(keycode)
                print(f"Secondary hotkey: '{key_name}' → {mode.name}")
            if self._secondary_devices:
                device_names = [d.name for d in self._secondary_devices]
                print(
                    f"Secondary hotkeys listening on {len(device_names)} device(s): {', '.join(device_names)}"
                )

        return True

    def stop(self):
        """Stop the FN key listener"""
        self._running = False

        # Wake the listener loop so it can exit
        self._wake_select()

        # Close devices
        with self._devices_lock:
            if self._device:
                try:
                    self._device.close()
                except Exception:
                    pass
                self._device = None
            for device in self._secondary_devices:
                try:
                    device.close()
                except Exception:
                    pass
            self._secondary_devices = []

        # Close the wake pipe
        self._close_wake_pipe()

        # Wait for threads to finish
        if self._device_monitor_thread:
            self._device_monitor_thread.join(timeout=1.0)
        if self._listener_thread:
            self._listener_thread.join(timeout=1.0)
        if self._callback_thread and self._callback_thread.is_alive():
            self._callback_queue.put(None)
            self._callback_thread.join(timeout=1.0)
            self._callback_thread = None

    def _start_callback_worker(self):
        """Run hotkey callbacks sequentially so state transitions stay ordered."""
        if self._callback_thread and self._callback_thread.is_alive():
            return

        def run_callbacks():
            while True:
                item = self._callback_queue.get()
                if item is None:
                    return

                action, mode = item
                try:
                    if action == "start" and self.on_start_recording:
                        self.on_start_recording(mode)
                    elif action == "stop" and self.on_stop_recording:
                        self.on_stop_recording()
                    elif action == "cancel" and self.on_cancel_recording:
                        self.on_cancel_recording()
                except Exception as exc:
                    if config.DEBUG:
                        print(f"Hotkey callback '{action}' failed: {exc}")

        self._callback_thread = threading.Thread(target=run_callbacks, daemon=True)
        self._callback_thread.start()

    def _enqueue_callback(self, action: str, mode: ProcessingMode | None = None):
        """Queue a hotkey callback for ordered delivery."""
        self._start_callback_worker()
        self._callback_queue.put((action, mode))

    def _close_wake_pipe(self):
        """Close the self-pipe used to wake select()"""
        if self._wake_pipe_r is not None:
            try:
                os.close(self._wake_pipe_r)
            except OSError:
                pass
            self._wake_pipe_r = None
        if self._wake_pipe_w is not None:
            try:
                os.close(self._wake_pipe_w)
            except OSError:
                pass
            self._wake_pipe_w = None

    def _wake_select(self):
        """Wake the select() call in the listener loop"""
        if self._wake_pipe_w is not None:
            try:
                os.write(self._wake_pipe_w, b"\x00")
            except (OSError, BrokenPipeError):
                pass

    def _device_monitor_loop(self):
        """Monitor for keyboard device add/remove events using pyudev.

        This runs in a separate thread and signals the listener loop
        when devices change so it can refresh the device list.

        Uses poll with timeout to allow clean shutdown.
        """
        try:
            import pyudev

            context = pyudev.Context()
            monitor = pyudev.Monitor.from_netlink(context)
            monitor.filter_by(subsystem="input")

            if config.DEBUG:
                print("Device monitor started (pyudev)")

            # Use timeout-based polling instead of blocking iter()
            while self._running:
                device = monitor.poll(timeout=1.0)
                if device is None:
                    # Timeout - check _running and continue
                    continue

                # Only interested in event devices (keyboards)
                if device.device_node and device.device_node.startswith("/dev/input/event"):
                    action = device.action
                    if action in ("add", "remove"):
                        if config.DEBUG:
                            print(f"Device {action}: {device.device_node}")

                        # Signal the listener loop to refresh devices
                        # Debouncing is handled in the listener loop
                        self._pending_refresh.set()
                        self._wake_select()

        except Exception as e:
            if self._running and config.DEBUG:
                print(f"Device monitor error: {e}")

    def _refresh_devices(self):
        """Refresh the device list after a hot-plug event.

        Called from the listener loop when _pending_refresh is set.
        Finds new devices OUTSIDE the lock (slow I/O), then updates
        the device list INSIDE the lock (fast).

        If no devices are found (e.g., device node not yet ready during hotplug),
        schedules a retry after a short delay.
        """
        if config.DEBUG:
            print("Refreshing keyboard devices...")

        # Find new devices OUTSIDE the lock (slow I/O operation)
        new_primary, new_secondary = self._find_keyboard_devices()

        # If discovery found nothing, schedule a retry — the device may not be ready yet
        if not new_primary and not new_secondary:
            if config.DEBUG:
                print("No devices found during refresh, scheduling retry...")
            self._schedule_refresh_retry()
            return

        # Update devices INSIDE the lock (fast operation)
        with self._devices_lock:
            # Close old devices
            if self._device:
                try:
                    self._device.close()
                except Exception:
                    pass
            for device in self._secondary_devices:
                try:
                    device.close()
                except Exception:
                    pass

            # Assign new devices
            self._device = new_primary
            self._secondary_devices = new_secondary

            if config.DEBUG:
                if self._device:
                    print(f"Primary device: {self._device.name}")
                if self._secondary_devices:
                    names = [d.name for d in self._secondary_devices]
                    print(f"Secondary devices: {', '.join(names)}")

    def _schedule_refresh_retry(self):
        """Schedule a delayed retry when device refresh found no devices.

        This handles the race where a device node exists in the kernel but
        isn't yet ready to be opened (common during USB hotplug).
        """

        def retry():
            if not self._running:
                return
            self._pending_refresh.set()
            self._last_refresh_time = 0  # Reset debounce so retry runs immediately
            self._wake_select()

        timer = threading.Timer(1.0, retry)
        timer.daemon = True
        timer.start()

    def _find_keyboard_devices(self):
        """Find keyboard devices for FN key, custom hotkey, and secondary hotkey.

        Returns:
            Tuple of (primary_device, secondary_devices):
            - primary_device: Laptop keyboard for FN/KEY_WAKEUP or custom hotkey
            - secondary_devices: List of ALL keyboards for secondary hotkey
        """
        return find_keyboard_devices(
            custom_hotkey_enabled=self._custom_hotkey_enabled,
            custom_hotkey_keycode=self._custom_hotkey_keycode,
            secondary_hotkeys=self._secondary_hotkeys,
            debug=config.DEBUG,
        )

    def _build_device_fd_map(self) -> dict:
        """Build a map of file descriptors to devices.

        Must be called with _devices_lock held.
        """
        return build_device_fd_map(self._device, self._secondary_devices)

    def _listen_loop(self):
        """Main event loop for evdev - reads from both primary and secondary devices.

        Supports hot-plug: when the device monitor signals a change via the wake pipe,
        this loop will refresh the device list and update the fd set.
        """
        try:
            import select

            from evdev import ecodes

            # Build initial list of devices to monitor
            with self._devices_lock:
                devices = self._build_device_fd_map()
                if config.DEBUG:
                    if self._device:
                        print(f"Listening for FN key on: {self._device.name}")
                    for sec_device in self._secondary_devices:
                        print(f"Listening for secondary hotkey on: {sec_device.name}")

            while self._running:
                # Check if we need to refresh devices (hot-plug event) with debouncing
                if self._pending_refresh.is_set():
                    elapsed_ms = (time.time() - self._last_refresh_time) * 1000
                    if elapsed_ms >= self._refresh_debounce_ms:
                        self._refresh_devices()
                        self._pending_refresh.clear()
                        self._last_refresh_time = time.time()
                        with self._devices_lock:
                            devices = self._build_device_fd_map()

                # Build fd list for select, including wake pipe
                fds = list(devices.keys())
                if self._wake_pipe_r is not None:
                    fds.append(self._wake_pipe_r)

                if not fds:
                    # No devices and no wake pipe - sleep briefly and retry
                    time.sleep(0.5)
                    continue

                # Wait for events (100ms timeout to check _running)
                try:
                    r, _, _ = select.select(fds, [], [], 0.1)
                except (ValueError, OSError):
                    # Invalid fd in list (device unplugged) - refresh
                    self._pending_refresh.set()
                    continue

                for fd in r:
                    # Check if it's the wake pipe
                    if fd == self._wake_pipe_r:
                        # Drain the pipe
                        try:
                            os.read(self._wake_pipe_r, 1024)
                        except (OSError, BlockingIOError):
                            pass
                        continue

                    device = devices.get(fd)
                    if device is None:
                        continue

                    # Read events from device
                    try:
                        events = list(device.read())
                    except OSError:
                        # Device unplugged - remove from local fd map immediately
                        # to prevent tight error loop, then trigger async refresh
                        if config.DEBUG:
                            print(f"Device read error (unplugged?): {device.name}")
                        devices.pop(fd, None)
                        self._pending_refresh.set()
                        self._wake_select()
                        continue

                    for event in events:
                        if not self._running:
                            return

                        # Only process key events
                        if event.type != ecodes.EV_KEY:
                            continue

                        # Track modifier key states
                        self._update_modifier_state(event.code, event.value)

                        # Check if this is the FN key (primary trigger)
                        is_fn_key = False
                        with self._devices_lock:
                            if device == self._device:
                                is_fn_key = event.code == KEY_WAKEUP or event.code == 464

                        # Check if this is the custom hotkey main key
                        is_custom_hotkey = (
                            self._custom_hotkey_enabled
                            and event.code == self._custom_hotkey_keycode
                        )

                        # Check if this is a secondary hotkey (on any device)
                        secondary_mode = self._secondary_hotkeys.get(event.code)

                        if is_fn_key:
                            # FN key: use modifier-based mode detection
                            if event.value == 1:  # Key down
                                self._secondary_hotkey_active = False
                                self._on_fn_key_down()
                            elif event.value == 0:  # Key up
                                self._on_fn_key_up()
                        elif is_custom_hotkey:
                            # Custom hotkey (e.g., alt+g, ctrl+shift+d)
                            # Only trigger if required modifiers are held
                            if event.value == 1:  # Key down
                                if self._is_custom_hotkey_modifiers_pressed():
                                    self._secondary_hotkey_active = False
                                    # Custom hotkey always uses BASIC mode (toggle only)
                                    self._current_mode = ProcessingMode.BASIC
                                    self._on_custom_hotkey_down()
                            elif event.value == 0:  # Key up
                                # Only process key up if we're in a recording state
                                # (to avoid processing releases for key presses that weren't triggered)
                                if self._state in (
                                    HotkeyState.RECORDING_TOGGLE,
                                    HotkeyState.TAP_DOWN,
                                    HotkeyState.WAITING_DOUBLE,
                                ):
                                    self._on_fn_key_up()
                        elif secondary_mode is not None:
                            # Secondary hotkey: use the specific mode for this key
                            if event.value == 1:  # Key down
                                self._secondary_hotkey_active = True
                                self._current_mode = secondary_mode
                                self._on_fn_key_down()
                            elif event.value == 0:  # Key up
                                self._on_fn_key_up()
                        # value == 2 is key repeat, ignored

        except Exception as e:
            if self._running and config.DEBUG:
                print(f"FN key listener error: {e}")

    def _update_modifier_state(self, keycode: int, value: int):
        """Track modifier key states for mode detection."""
        pressed = value == 1  # 1 = press, 0 = release, 2 = repeat

        if keycode == KEY_SPACE:
            self._space_pressed = pressed
        elif keycode in (KEY_LEFTCTRL, KEY_RIGHTCTRL):
            self._ctrl_pressed = pressed
        elif keycode in (KEY_LEFTSHIFT, KEY_RIGHTSHIFT):
            self._shift_pressed = pressed
        elif keycode in (KEY_LEFTALT, KEY_RIGHTALT):
            self._alt_pressed = pressed

    def _detect_mode(self) -> ProcessingMode:
        """Detect processing mode based on current modifier states.

        Priority order:
        - FN + Ctrl + Shift → TRANSLATE_REFORMAT (Cyan)
        - FN + Ctrl → TRANSLATION (Green)
        - FN + Shift → ACT_ON_TEXT (Magenta)
        - FN + Alt → REFORMULATION (Purple)
        - FN + Space → RAW (Yellow)
        - FN only → BASIC (Orange)
        """
        if self._ctrl_pressed and self._shift_pressed and advanced_modes_enabled():
            return ProcessingMode.TRANSLATE_REFORMAT
        if self._ctrl_pressed:
            return ProcessingMode.TRANSLATION
        if self._shift_pressed and advanced_modes_enabled():
            return ProcessingMode.ACT_ON_TEXT
        if self._alt_pressed and advanced_modes_enabled():
            return ProcessingMode.REFORMULATION
        if self._space_pressed and advanced_modes_enabled():
            return ProcessingMode.RAW
        return ProcessingMode.BASIC

    def _on_custom_hotkey_down(self):
        """Handle custom hotkey press (e.g., alt+g, ctrl+shift+d).

        Custom hotkeys use toggle-only behavior:
        - First press with modifiers held: Start recording
        - Second press with modifiers held: Stop recording
        """
        now = time.time()

        with self._state_lock:
            if self._state == HotkeyState.IDLE:
                self._key_down_time = now
                # Custom hotkey uses toggle mode
                self._state = HotkeyState.RECORDING_TOGGLE
                self._toggle_first_release = True  # Ignore first release
                self._trigger_start_recording()

            elif self._state == HotkeyState.RECORDING_TOGGLE:
                # In toggle mode, second key press stops recording
                self._key_down_time = now
                self._state = HotkeyState.IDLE
                self._trigger_stop_recording()

    def _on_fn_key_down(self):
        """Handle FN key press.

        Behavior depends on mode:
        - BASIC (FN only): Double-tap to start/stop recording
        - Advanced modes (FN+modifier or secondary hotkey): Toggle (press to start, press to stop)
        """
        now = time.time()

        with self._state_lock:
            if self._state == HotkeyState.IDLE:
                self._key_down_time = now

                # For secondary hotkeys, mode is already set; for FN key, detect from modifiers
                if not self._secondary_hotkey_active:
                    self._current_mode = self._detect_mode()

                # Advanced modes (with modifiers or secondary hotkey) use toggle-only behavior
                # Secondary hotkeys always use toggle behavior (even for BASIC mode)
                if self._current_mode != ProcessingMode.BASIC or self._secondary_hotkey_active:
                    self._state = HotkeyState.RECORDING_TOGGLE
                    self._toggle_first_release = True  # Ignore first release
                    self._trigger_start_recording()
                else:
                    # BASIC mode via FN: Wait for tap release, then double-tap
                    self._state = HotkeyState.TAP_DOWN

            elif self._state == HotkeyState.WAITING_DOUBLE:
                # Second tap within window - enter toggle mode
                if now - self._key_up_time < self._double_tap_window:
                    self._state = HotkeyState.RECORDING_TOGGLE
                    self._toggle_first_release = False  # Double-tap toggle stops on next tap
                    self._trigger_start_recording()
                else:
                    # Window expired, treat as new press
                    self._key_down_time = now
                    if not self._secondary_hotkey_active:
                        self._current_mode = self._detect_mode()
                    if self._current_mode != ProcessingMode.BASIC or self._secondary_hotkey_active:
                        self._state = HotkeyState.RECORDING_TOGGLE
                        self._toggle_first_release = True
                        self._trigger_start_recording()
                    else:
                        self._state = HotkeyState.TAP_DOWN

            elif self._state == HotkeyState.RECORDING_TOGGLE:
                # In toggle mode, second key press stops recording
                self._key_down_time = now
                self._state = HotkeyState.IDLE
                self._trigger_stop_recording()

    def _on_fn_key_up(self):
        """Handle FN key release"""
        now = time.time()

        with self._state_lock:
            if self._state == HotkeyState.TAP_DOWN:
                # First tap completed - wait for second tap
                self._key_up_time = now
                self._state = HotkeyState.WAITING_DOUBLE
                self._start_double_tap_timer()

            elif self._state == HotkeyState.RECORDING_TOGGLE:
                # Toggle mode: recording continues until next key press
                # Just track timing, stop happens on next key DOWN
                self._key_up_time = now

    def _start_double_tap_timer(self):
        """Start timer for double-tap window"""

        def check_timeout():
            time.sleep(self._double_tap_window)
            with self._state_lock:
                if self._state == HotkeyState.WAITING_DOUBLE:
                    # Timeout - return to idle (single tap does nothing)
                    self._state = HotkeyState.IDLE

        timer = threading.Thread(target=check_timeout, daemon=True)
        timer.start()

    def _trigger_start_recording(self):
        """Trigger recording start callback with current mode"""
        if self.on_start_recording:
            self._enqueue_callback("start", self._current_mode)

    def _trigger_stop_recording(self):
        """Trigger recording stop callback (will process audio)"""
        if self.on_stop_recording:
            self._enqueue_callback("stop")

    def _trigger_cancel_recording(self):
        """Trigger recording cancel callback (discard audio, tap detected)"""
        if self.on_cancel_recording:
            self._enqueue_callback("cancel")

    @property
    def state(self) -> HotkeyState:
        """Get current state (thread-safe)"""
        with self._state_lock:
            return self._state

    @property
    def is_recording(self) -> bool:
        """Check if currently in a recording state"""
        with self._state_lock:
            return self._state == HotkeyState.RECORDING_TOGGLE

    @property
    def is_toggle_mode(self) -> bool:
        """Check if in toggle (locked) recording mode"""
        with self._state_lock:
            return self._state == HotkeyState.RECORDING_TOGGLE

    @property
    def current_mode(self) -> ProcessingMode:
        """Get the current processing mode"""
        with self._state_lock:
            return self._current_mode
