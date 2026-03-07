"""Entry point for ``python -m dicton`` and the console script."""

from __future__ import annotations

import sys

from . import __version__


def main() -> None:
    """Dispatch the CLI while keeping ``--version`` lightweight."""
    if "--version" in sys.argv[1:]:
        print(f"Dicton v{__version__}")
        return

    from .main import main as app_main

    app_main()


if __name__ == "__main__":
    main()
