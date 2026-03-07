"""Entry point for ``python -m dicton`` and the console script."""

from __future__ import annotations

import argparse
import sys

from . import __version__


def _run_config_ui(argv: list[str]) -> None:
    """Launch the config UI without importing the full app stack."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--config-ui", action="store_true")
    parser.add_argument("--config-port", type=int, default=6873)
    args, _ = parser.parse_known_args(argv)

    from .config_server import run_config_server

    run_config_server(port=args.config_port)


def main() -> None:
    """Dispatch the CLI while keeping ``--version`` lightweight."""
    argv = sys.argv[1:]

    if "--version" in argv:
        print(f"Dicton v{__version__}")
        return

    if "--config-ui" in argv:
        _run_config_ui(argv)
        return

    from .main import main as app_main

    app_main()


if __name__ == "__main__":
    main()
