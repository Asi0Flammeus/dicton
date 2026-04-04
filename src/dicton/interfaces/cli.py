#!/usr/bin/env python3
"""CLI commands and runtime startup for Dicton."""

from __future__ import annotations

import argparse
import os
import signal
import warnings

os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
warnings.filterwarnings("ignore")

from ..adapters.config.config_env import load_app_config
from ..orchestration.container import build_runtime_service
from ..shared.platform_utils import IS_WINDOWS


def show_latency_report() -> None:
    """Show latency report from log file."""
    from ..adapters.config.latency import LatencyTracker

    tracker = LatencyTracker(enabled=True)
    count = tracker.load_from_log()

    if count == 0:
        print("No latency data found.")
        print(f"Log file: {tracker.log_path}")
        print("\nRun dicton with DEBUG=true to collect latency data.")
        return

    print(f"\n📊 Dicton Latency Report ({count} sessions)")
    tracker.print_summary()
    print(f"\nLog file: {tracker.log_path}")


def clear_latency_log() -> None:
    """Clear the latency log file."""
    from ..adapters.config.latency import LatencyTracker

    tracker = LatencyTracker(enabled=True)
    tracker.clear_log()
    print(f"✓ Cleared latency log: {tracker.log_path}")


def build_parser() -> argparse.ArgumentParser:
    app_cfg = load_app_config()
    epilog = """
Hotkeys (default):
  FN (double-tap)  Toggle recording (direct transcription)
  FN + Ctrl        Translate to English

Examples:
  dicton                  Start dictation service
  dicton --config         Open the guided setup flow
  dicton --config-ui      Open settings in browser
  dicton --benchmark      Show latency statistics
  dicton --check-update   Check for new version
  dicton --clear-log      Clear latency history
"""
    if app_cfg.enable_advanced_modes:
        epilog = """
Hotkeys (FN key mode):
  FN (double-tap)  Toggle recording (direct transcription)
  FN + Ctrl        Translate to English
  FN + Shift       Act on Text
  FN + Alt         LLM Reformulation
  FN + Space       Raw mode

Examples:
  dicton                  Start dictation service
  dicton --config         Open the guided setup flow
  dicton --config-ui      Open settings in browser
  dicton --benchmark      Show latency statistics
  dicton --check-update   Check for new version
  dicton --clear-log      Clear latency history
"""

    parser = argparse.ArgumentParser(
        description="Dicton: Voice-to-text dictation tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=epilog,
    )
    parser.add_argument(
        "--benchmark", action="store_true", help="Show latency report from previous sessions"
    )
    parser.add_argument("--check-update", action="store_true", help="Check for available updates")
    parser.add_argument("--clear-log", action="store_true", help="Clear the latency log file")
    parser.add_argument("--version", action="store_true", help="Show version information")
    parser.add_argument(
        "--config", action="store_true", help="Launch the guided setup flow in browser"
    )
    parser.add_argument(
        "--config-ui", action="store_true", help="Launch configuration UI in browser"
    )
    parser.add_argument(
        "--config-port", type=int, default=6873, help="Port for config UI server (default: 6873)"
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()

    if args.version:
        from . import __version__

        print(f"Dicton v{__version__}")
        return

    if args.config or args.config_ui:
        try:
            from .config_server import run_config_server

            run_config_server(port=args.config_port)
        except ImportError:
            print("Error: Configuration UI requires additional dependencies.")
            print("Install with: pip install dicton[configui]")
        return

    if args.check_update:
        from ..adapters.config.update_checker import check_for_updates, print_update_notification

        print("Checking for updates...")
        update = check_for_updates(force=True)
        if update:
            print_update_notification(update)
        else:
            from . import __version__

            print(f"✓ You are running the latest version (v{__version__})")
        return

    if args.clear_log:
        clear_latency_log()
        return

    if args.benchmark:
        show_latency_report()
        return

    from ..shared.singleton import acquire_instance_lock

    _lock = acquire_instance_lock()
    if _lock is None:
        print("⚠ Dicton is already running. Exiting.")
        return

    from ..shared.log_setup import setup_logging

    log_path = setup_logging()

    app = build_runtime_service(log_path=log_path)

    def signal_handler(sig, frame):
        app.request_shutdown()

    signal.signal(signal.SIGINT, signal_handler)
    if not IS_WINDOWS:
        signal.signal(signal.SIGTERM, signal_handler)

    app.run()
