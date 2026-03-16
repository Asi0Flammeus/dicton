"""Entry point for ``python -m dicton`` and the console script."""

from __future__ import annotations

import argparse
import sys

from . import __version__


def _run_config_ui(argv: list[str]) -> None:
    """Launch the config UI without importing the full app stack."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--config", action="store_true")
    parser.add_argument("--config-ui", action="store_true")
    parser.add_argument("--config-port", type=int, default=6873)
    parser.add_argument("--reset", action="store_true")
    args, _ = parser.parse_known_args(argv)

    if args.reset:
        from .shared.app_paths import get_user_env_path

        env_path = get_user_env_path()
        if env_path.exists():
            env_path.unlink()
            print(f"Reset: deleted {env_path}")

    from .interfaces.config_server import run_config_server

    run_config_server(port=args.config_port)


def main() -> None:
    """Dispatch the CLI while keeping ``--version`` lightweight."""
    argv = sys.argv[1:]

    if "--version" in argv:
        print(f"Dicton v{__version__}")
        return

    if "--config" in argv or "--config-ui" in argv:
        _run_config_ui(argv)
        return

    from .interfaces.cli import main as app_main

    app_main()


if __name__ == "__main__":
    main()
