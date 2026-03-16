"""File logging for headless operation.

Dicton runs via XDG autostart with Terminal=false — all print() output goes
to /dev/null.  This module installs a TeeWriter on stdout/stderr so every
print() also lands in ~/.local/share/dicton/dicton.log without touching any
call site.
"""

from __future__ import annotations

import io
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from .app_paths import get_log_path

_MAX_LOG_BYTES = 2 * 1024 * 1024  # 2 MB


class _TeeWriter(io.TextIOBase):
    """Write to *both* the original stream and a log file.

    When there is no TTY (headless autostart), the original stream is
    effectively /dev/null — writes still go to the log file.

    ``fileno()`` delegates to the original stream so fd-level ops like
    ``os.dup2(devnull, 2)`` in ``suppress_stderr()`` keep working.
    """

    def __init__(self, original: io.TextIOBase, log_file: io.TextIOBase):
        self._original = original
        self._log_file = log_file

    # -- io.TextIOBase interface ------------------------------------------

    def write(self, s: str) -> int:
        try:
            self._original.write(s)
        except Exception:
            pass
        try:
            self._log_file.write(s)
            self._log_file.flush()
        except Exception:
            pass
        return len(s)

    def flush(self) -> None:
        try:
            self._original.flush()
        except Exception:
            pass
        try:
            self._log_file.flush()
        except Exception:
            pass

    def fileno(self) -> int:
        return self._original.fileno()

    @property
    def encoding(self) -> str:  # type: ignore[override]
        return getattr(self._original, "encoding", "utf-8")

    @property
    def errors(self) -> str | None:  # type: ignore[override]
        return getattr(self._original, "errors", None)

    def isatty(self) -> bool:
        return self._original.isatty()

    def readable(self) -> bool:
        return False

    def writable(self) -> bool:
        return True


def _rotate_log(log_path: Path) -> None:
    """Rotate if *log_path* exceeds ``_MAX_LOG_BYTES``."""
    try:
        if log_path.exists() and log_path.stat().st_size > _MAX_LOG_BYTES:
            backup = log_path.with_suffix(".log.1")
            log_path.replace(backup)
    except OSError:
        pass


def setup_logging() -> Path:
    """Install file logging and return the log file path.

    * Rotates the log if it exceeds 2 MB.
    * Wraps stdout/stderr with :class:`_TeeWriter`.
    * Configures :mod:`logging` so existing ``getLogger()`` calls emit to
      the same file.

    Returns the log file :class:`Path` (useful for the tray "View Log" action).
    """
    log_path = get_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)

    _rotate_log(log_path)

    log_file = open(log_path, "a", encoding="utf-8")  # noqa: SIM115

    # Session separator
    now = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    log_file.write(f"\n{'=' * 60}\n")
    log_file.write(f"  Dicton session started — {now}\n")
    log_file.write(f"{'=' * 60}\n\n")
    log_file.flush()

    sys.stdout = _TeeWriter(sys.__stdout__, log_file)  # type: ignore[assignment]
    sys.stderr = _TeeWriter(sys.__stderr__, log_file)  # type: ignore[assignment]

    # Activate the ~8 existing logging.getLogger() calls in the codebase
    from .config import config

    level = logging.DEBUG if config.DEBUG else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(name)s %(levelname)s: %(message)s",
        stream=sys.stderr,
        force=True,
    )

    return log_path
