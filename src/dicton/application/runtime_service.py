"""Application service for process runtime lifecycle."""

from __future__ import annotations

import logging
import signal
import threading
from pathlib import Path

from ..config import config
from ..platform_utils import IS_LINUX, IS_WINDOWS


class RuntimeService:
    """Own application startup, runtime wait loop, and shutdown."""

    def __init__(
        self, session_service, keyboard, recognizer, app_config, log_path=None, chunk_manager=None
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

        if not self._recognizer._provider_available:
            print("❌ No STT provider configured - dictation will not work!")

    def _init_fn_handler(self) -> bool:
        if not IS_LINUX:
            return False

        hotkey_base = config.HOTKEY_BASE.lower()
        if hotkey_base not in ("fn", "custom"):
            return False

        try:
            from ..fn_key_handler import FnKeyHandler

            self._fn_handler = FnKeyHandler(
                on_start_recording=self._session_service.start_recording,
                on_stop_recording=self._session_service.stop_recording,
                on_cancel_recording=self._session_service.cancel_recording,
            )
            return self._fn_handler.start()
        except ImportError:
            print("FN key support requires evdev: pip install dicton[fnkey]")
            return False
        except Exception as exc:
            if self._app_config.debug:
                print(f"FN handler init failed: {exc}")
            return False

    def run(self) -> None:
        print("\n" + "=" * 50)
        print("🚀 Dicton")
        print("=" * 50)

        if self._check_vpn_active():
            print("⚠ VPN detected - API calls may fail or timeout")
            print("  If dictation hangs, try disconnecting VPN")

        try:
            from ..update_checker import check_for_updates_async

            check_for_updates_async()
        except ImportError:
            pass

        self._use_fn_key = self._init_fn_handler()
        self._init_tray()

        if self._use_fn_key:
            print("Hotkey: FN key (hold=PTT, double-tap=toggle)")
            print("Modes: FN=Direct transcription, FN+Ctrl=Translate to English")
            if config.ENABLE_ADVANCED_MODES:
                print("Advanced: FN+Alt=Reformulation, FN+Shift=Act on Text, FN+Space=Raw")
        else:
            print(f"Hotkey: {config.HOTKEY_MODIFIER}+{config.HOTKEY_KEY}")
            try:
                self._keyboard.start()
            except ImportError as exc:
                print("❌ No usable hotkey backend is available.")
                if IS_LINUX:
                    print(
                        "Configure a Linux hotkey in `dicton --config-ui` and ensure evdev access, or run under an X session for the legacy listener."
                    )
                else:
                    print(str(exc))
                return

        print(f"STT: {self._recognizer.provider_name}")
        print("\nPress hotkey to start/stop recording")
        print("Press Ctrl+C to quit")
        print("=" * 50 + "\n")

        hotkey_display = (
            "FN" if self._use_fn_key else f"{config.HOTKEY_MODIFIER}+{config.HOTKEY_KEY}"
        )
        from ..ui_feedback import notify

        notify("Dicton Ready", f"Press {hotkey_display}")

        try:
            if IS_WINDOWS:
                self._shutdown_event.wait()
            else:
                signal.pause()
        except KeyboardInterrupt:
            pass

        self.shutdown()

    def _init_tray(self) -> None:
        try:
            from ..tray import DictonTray

            self._tray = DictonTray(
                on_quit=self.request_shutdown,
                on_toggle_debug=self._toggle_debug,
                log_path=self._log_path,
            )
            self._session_service.add_state_observer(self._tray.on_state_change)
            self._tray.start()
        except ImportError:
            pass
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

        from ..stt_factory import clear_provider_cache

        clear_provider_cache()

        from ..llm import cleanup as llm_cleanup

        llm_cleanup()

        print("✓ Done")

    def request_shutdown(self) -> None:
        self._shutdown_event.set()

    def _check_vpn_active(self) -> bool:
        if IS_WINDOWS:
            return False

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
