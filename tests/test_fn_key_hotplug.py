"""Tests for FN key handler hot-plug detection.

Tests cover:
- threading.Event synchronization
- Device refresh with mock devices
- Poll timeout shutdown behavior
- Debouncing rapid events
- Graceful degradation without pyudev
"""

import sys
import threading
import time
from unittest.mock import MagicMock, patch

import pytest


def create_mock_evdev():
    """Create a mock evdev module for testing."""
    mock_evdev = MagicMock()
    mock_evdev.InputDevice = MagicMock()
    mock_evdev.list_devices = MagicMock(return_value=[])
    mock_evdev.ecodes = MagicMock()
    mock_evdev.ecodes.EV_KEY = 1
    mock_evdev.ecodes.KEY_A = 30
    mock_evdev.ecodes.KEY_Z = 44
    return mock_evdev


@pytest.fixture
def mock_evdev_module():
    """Fixture to mock evdev module."""
    mock_evdev = create_mock_evdev()
    with patch.dict(sys.modules, {"evdev": mock_evdev, "evdev.ecodes": mock_evdev.ecodes}):
        yield mock_evdev


@pytest.fixture
def fn_handler(mock_evdev_module):
    """Fixture to create FnKeyHandler with mocked dependencies."""
    # Also mock pyudev as optional
    with patch.dict(sys.modules, {"pyudev": MagicMock()}):
        # Clear any cached imports
        if "dicton.fn_key_handler" in sys.modules:
            del sys.modules["dicton.fn_key_handler"]

        from dicton.fn_key_handler import FnKeyHandler

        handler = FnKeyHandler()
        yield handler


class TestPendingRefreshEvent:
    """Test threading.Event synchronization for _pending_refresh."""

    def test_event_initial_state(self, fn_handler):
        """Event should start in unset state."""
        assert not fn_handler._pending_refresh.is_set()

    def test_event_set_and_clear(self, fn_handler):
        """Event should be settable and clearable."""
        fn_handler._pending_refresh.set()
        assert fn_handler._pending_refresh.is_set()

        fn_handler._pending_refresh.clear()
        assert not fn_handler._pending_refresh.is_set()

    def test_event_thread_safety(self, fn_handler):
        """Event should be safely accessible from multiple threads."""
        results = []

        def setter():
            for _ in range(100):
                fn_handler._pending_refresh.set()
                time.sleep(0.001)

        def checker():
            for _ in range(100):
                results.append(fn_handler._pending_refresh.is_set())
                time.sleep(0.001)

        t1 = threading.Thread(target=setter)
        t2 = threading.Thread(target=checker)

        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # Should have completed without exceptions
        assert len(results) == 100


class TestRefreshDevicesLocking:
    """Test that _refresh_devices performs I/O outside the lock."""

    def test_find_devices_called_outside_lock(self, fn_handler):
        """_find_keyboard_devices should be called outside _devices_lock."""
        # Track when find_devices is called relative to lock
        call_order = []

        def mock_find():
            # Check if lock is held
            acquired = fn_handler._devices_lock.acquire(blocking=False)
            if acquired:
                call_order.append("find_outside_lock")
                fn_handler._devices_lock.release()
            else:
                call_order.append("find_inside_lock")
            return None, []

        with patch.object(fn_handler, "_find_keyboard_devices", mock_find):
            fn_handler._refresh_devices()

        # _find_keyboard_devices should be called outside the lock
        assert "find_outside_lock" in call_order


class TestDebouncing:
    """Test debouncing of rapid hot-plug events."""

    def test_debounce_timing_initialization(self, fn_handler):
        """Debounce fields should be initialized."""
        assert fn_handler._last_refresh_time == 0
        assert fn_handler._refresh_debounce_ms == 500

    def test_rapid_events_debounced(self, fn_handler):
        """Rapid events within debounce window should not trigger multiple refreshes."""
        refresh_count = [0]

        def counting_refresh():
            refresh_count[0] += 1

        # Simulate the debounce logic from _listen_loop
        def simulate_debounced_refresh():
            if fn_handler._pending_refresh.is_set():
                elapsed_ms = (time.time() - fn_handler._last_refresh_time) * 1000
                if elapsed_ms >= fn_handler._refresh_debounce_ms:
                    counting_refresh()
                    fn_handler._pending_refresh.clear()
                    fn_handler._last_refresh_time = time.time()

        # First refresh should go through
        fn_handler._pending_refresh.set()
        simulate_debounced_refresh()
        assert refresh_count[0] == 1

        # Immediate second event should be debounced
        fn_handler._pending_refresh.set()
        simulate_debounced_refresh()
        assert refresh_count[0] == 1  # Still 1, debounced

        # After debounce window, should go through
        fn_handler._last_refresh_time = time.time() - 1  # Simulate 1s ago
        fn_handler._pending_refresh.set()
        simulate_debounced_refresh()
        assert refresh_count[0] == 2


class TestGracefulDegradation:
    """Test behavior when pyudev is not available."""

    def test_works_without_pyudev(self, mock_evdev_module):
        """Handler should work without pyudev (no hot-plug detection)."""
        # Import without pyudev in sys.modules
        with patch.dict(sys.modules, {"pyudev": None}):
            if "dicton.fn_key_handler" in sys.modules:
                del sys.modules["dicton.fn_key_handler"]

            from dicton.fn_key_handler import FnKeyHandler

            handler = FnKeyHandler()
            # Should initialize successfully
            assert handler._pending_refresh is not None
            assert handler._devices_lock is not None

    def test_pyudev_flag_initial_state(self, fn_handler):
        """_pyudev_available should be False initially (set during start())."""
        assert fn_handler._pyudev_available is False


class TestMonitorPollTimeout:
    """Test that monitor.poll uses timeout for clean shutdown."""

    def test_poll_with_timeout_allows_shutdown(self, mock_evdev_module):
        """Monitor loop should check _running after poll timeout."""
        # Create a mock pyudev module
        mock_monitor = MagicMock()
        # First call returns None (timeout), second would block but we stop
        mock_monitor.poll = MagicMock(side_effect=[None, None])

        mock_context = MagicMock()
        mock_pyudev = MagicMock()
        mock_pyudev.Context.return_value = mock_context
        mock_pyudev.Monitor.from_netlink.return_value = mock_monitor

        with patch.dict(sys.modules, {"pyudev": mock_pyudev}):
            if "dicton.fn_key_handler" in sys.modules:
                del sys.modules["dicton.fn_key_handler"]

            from dicton.fn_key_handler import FnKeyHandler

            handler = FnKeyHandler()
            handler._pyudev_available = True
            handler._running = True

            # Start monitor in thread
            monitor_thread = threading.Thread(target=handler._device_monitor_loop, daemon=True)
            monitor_thread.start()

            # Give it time to call poll once
            time.sleep(0.1)

            # Signal shutdown
            handler._running = False

            # Thread should exit within poll timeout (1s) + some margin
            monitor_thread.join(timeout=2.0)
            assert not monitor_thread.is_alive(), "Monitor thread did not exit cleanly"

    def test_monitor_handles_device_events(self, mock_evdev_module):
        """Monitor should set _pending_refresh on device add/remove."""
        mock_device = MagicMock()
        mock_device.device_node = "/dev/input/event99"
        mock_device.action = "add"

        mock_monitor = MagicMock()
        # Return device, then None to exit
        mock_monitor.poll = MagicMock(side_effect=[mock_device, None, None])

        mock_context = MagicMock()
        mock_pyudev = MagicMock()
        mock_pyudev.Context.return_value = mock_context
        mock_pyudev.Monitor.from_netlink.return_value = mock_monitor

        with patch.dict(sys.modules, {"pyudev": mock_pyudev}):
            if "dicton.fn_key_handler" in sys.modules:
                del sys.modules["dicton.fn_key_handler"]

            from dicton.fn_key_handler import FnKeyHandler

            handler = FnKeyHandler()
            handler._pyudev_available = True
            handler._running = True

            # Mock _wake_select to avoid pipe issues
            handler._wake_select = MagicMock()

            # Start monitor in thread
            monitor_thread = threading.Thread(target=handler._device_monitor_loop, daemon=True)
            monitor_thread.start()

            # Give it time to process
            time.sleep(0.2)

            # Stop and wait
            handler._running = False
            monitor_thread.join(timeout=2.0)

            # Should have set pending refresh
            assert handler._pending_refresh.is_set()
            # Should have called wake_select
            handler._wake_select.assert_called()
