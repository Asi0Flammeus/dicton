"""Cross-platform Fn key facade."""

from __future__ import annotations

import sys
from collections.abc import Callable

FN_KEYCODES = {143, 464, 465, 466}

if sys.platform == "linux":
    from ._linux import FN_KEYCODES as FN_KEYCODES
    from ._linux import FnKeyListener as FnKeyListener
    from ._linux import capture_keycode as capture_keycode
else:

    def capture_keycode(timeout_s: float = 5.0) -> tuple[int, str] | None:
        _ = timeout_s
        return None

    class FnKeyListener:
        def __init__(
            self,
            on_tap: Callable[[], None],
            keycodes: set[int] | None = None,
        ) -> None:
            _ = (on_tap, keycodes)

        def start(self) -> bool:
            return False

        def stop(self) -> None:
            return None
