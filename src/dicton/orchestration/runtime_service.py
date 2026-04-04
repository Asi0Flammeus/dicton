"""Application service for process runtime lifecycle."""

from __future__ import annotations

import logging
import threading
from pathlib import Path

from ..shared.config import config


class _NullNotifications:
    def notify(self, title: str, message: str, timeout: int = 2) -> None:
        pass


class RuntimeService:
    """Own application startup, runtime wait loop, and shutdown."""

    def __init__(
        self,
        session_service,
        keyboard,
        recognizer,
        app_config,
        log_path=None,
        chunk_manager=None,
        notification_service=None,
    ):
        self._session_service = session_service
        self._keyboard = keyboard
        self._recognizer = recognizer
        self._app_config = app_config
        self._log_path: Path | None = log_path
        self._chunk_manager = chunk_manager
        self._shutdown_event = threading.Event()
        self._fn_handler = None
        self._tray = None
        self._use_fn_key = False
        self._notifications = (
            notification_service if notification_service is not None else _NullNotifications()
        )

        if not self._recognizer._provider_available:
            print("❌ No STT provider configured - dictation will not work!")

    def _init_fn_handler(self) -> bool:
        hotkey_base = config.HOTKEY_BASE.lower()
        if hotkey_base not in ("fn", "custom"):
            return False

        try:
            from ..adapters.input.fn.handler import FnKeyHandler

            self._fn_handler = FnKeyHandler(
                on_start_recording=self._session_service.start_recording,
                on_stop_recording=self._session_service.stop_recording,
                on_cancel_recording=self._session_service.cancel_recording,
                double_tap_window_ms=config.HOTKEY_DOUBLE_TAP_WINDOW_MS,
                debug=config.DEBUG,
                secondary_hotkey=config.SECONDARY_HOTKEY,
                secondary_hotkey_translation=config.SECONDARY_HOTKEY_TRANSLATION,
                secondary_hotkey_act_on_text=config.SECONDARY_HOTKEY_ACT_ON_TEXT,
                hotkey_base=config.HOTKEY_BASE,
                custom_hotkey_value=config.CUSTOM_HOTKEY_VALUE,
            )
            return self._fn_handler.start()
        except ImportError:
            from ..shared.platform_utils import IS_WAYLAND, IS_X11, WAYLAND_COMPOSITOR

            print("FN key backend: evdev not available in this build")
            print(
                f"   Platform: X11={IS_X11}, Wayland={IS_WAYLAND}, compositor={WAYLAND_COMPOSITOR}"
            )
            return False
        except Exception as exc:
            from ..shared.platform_utils import IS_WAYLAND, IS_X11, WAYLAND_COMPOSITOR

            print(f"FN handler init failed: {exc}")
            print(
                f"   Platform: X11={IS_X11}, Wayland={IS_WAYLAND}, compositor={WAYLAND_COMPOSITOR}"
            )
            return False

    def run(self) -> None:
        print("\n" + "=" * 50)
        print("🚀 Dicton")
        print("=" * 50)

        from ..shared.platform_utils import IS_WAYLAND, IS_X11, WAYLAND_COMPOSITOR

        if IS_X11:
            print("Display: X11")
        elif IS_WAYLAND:
            print(f"Display: Wayland ({WAYLAND_COMPOSITOR})")

        if self._check_vpn_active():
            print("⚠ VPN detected - API calls may fail or timeout")
            print("  If dictation hangs, try disconnecting VPN")

        try:
            from ..shared.update_checker import check_for_updates_async

            check_for_updates_async()
        except ImportError:
            pass

        self._use_fn_key = self._init_fn_handler()
        self._init_tray()

        if self._use_fn_key:
            print("Hotkey: FN key (double-tap=toggle)")
            print("Modes: FN=Direct transcription, FN+Ctrl=Translate to English")
            if config.ENABLE_ADVANCED_MODES:
                print("Advanced: FN+Alt=Reformulation, FN+Shift=Act on Text, FN+Space=Raw")
        else:
            print(f"Hotkey: {config.HOTKEY_MODIFIER}+{config.HOTKEY_KEY}")
            try:
                self._keyboard.start()
            except ImportError as exc:
                from ..shared.platform_utils import IS_WAYLAND, IS_X11, WAYLAND_COMPOSITOR

                print("❌ No usable hotkey backend is available.")
                print(
                    f"   Platform: X11={IS_X11}, Wayland={IS_WAYLAND}, compositor={WAYLAND_COMPOSITOR}"
                )
                print(f"   Error: {exc}")
                if IS_WAYLAND:
                    print("\n💡 On Wayland, pynput requires XWayland.")
                    print(
                        "   Recommended: use HOTKEY_BASE=fn (evdev-based, works natively on Wayland)"
                    )
                    print("   Or log in with 'Ubuntu on Xorg' session.")
                print("\nTry one of the following resolutions:")
                print(" * Install evdev: pip install evdev (for FN key / custom hotkey support)")
                print(" * Add your user to the 'input' group: sudo usermod -aG input $USER")
                print(" * If using Wayland, ensure XWayland is running and DISPLAY is set")
                return

        print(f"STT: {self._recognizer.provider_name}")
        print("\nPress hotkey to start/stop recording")
        print("Press Ctrl+C to quit")
        print("=" * 50 + "\n")

        hotkey_display = (
            "FN" if self._use_fn_key else f"{config.HOTKEY_MODIFIER}+{config.HOTKEY_KEY}"
        )
        self._notifications.notify("Dicton Ready", f"Press {hotkey_display}")

        try:
            self._shutdown_event.wait()
        except KeyboardInterrupt:
            pass

        self.shutdown()

    def _init_tray(self) -> None:
        try:
            from ..adapters.ui.tray_factory import get_system_tray

            self._tray = get_system_tray(
                on_quit=self.request_shutdown,
                on_toggle_debug=self._toggle_debug,
                log_path=self._log_path,
                initial_debug=config.DEBUG,
            )
            self._session_service.add_state_observer(self._tray.on_state_change)
            self._tray.start()
        except Exception:
            logging.getLogger(__name__).debug("Tray init failed", exc_info=True)

    def _toggle_debug(self) -> bool:
        config.DEBUG = not config.DEBUG
        level = logging.DEBUG if config.DEBUG else logging.WARNING
        logging.getLogger().setLevel(level)
        print(f"Debug mode: {'ON' if config.DEBUG else 'OFF'}")
        return config.DEBUG

    def shutdown(self) -> None:
        print("\nShutting down...")
        self._shutdown_event.set()

        if self._chunk_manager is not None:
            self._chunk_manager.close()

        if self._tray:
            self._tray.stop()

        if self._fn_handler:
            self._fn_handler.stop()

        self._keyboard.stop()
        self._recognizer.cleanup()

        from ..adapters.stt.factory import clear_provider_cache

        clear_provider_cache()

        from ..adapters.llm.factory import cleanup as llm_cleanup

        llm_cleanup()

        print("✓ Done")

    def request_shutdown(self) -> None:
        self._shutdown_event.set()

    def _check_vpn_active(self) -> bool:
        try:
            import subprocess

            result = subprocess.run(
                ["ip", "link", "show"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            vpn_interfaces = ["tun", "tap", "wg", "vpn", "proton", "nord", "mullvad"]
            return any(iface in result.stdout.lower() for iface in vpn_interfaces)
        except Exception:
            return False
