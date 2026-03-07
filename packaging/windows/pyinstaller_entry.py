"""PyInstaller entrypoint for Dicton.

This avoids executing ``dicton/__main__.py`` as a bare script, which would
break its relative imports in a frozen application.
"""

from dicton.__main__ import main

if __name__ == "__main__":
    main()
