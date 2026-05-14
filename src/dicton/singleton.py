"""Single-instance file-lock to prevent two daemons paste-racing each other."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import IO

from platformdirs import user_runtime_dir


def acquire() -> IO[str] | None:
    """Try to acquire the exclusive lock. Returns the held file handle, or None
    if another instance already holds it. Keep the handle alive for the lifetime
    of the process; closing it releases the lock."""
    if sys.platform == "win32":
        return _acquire_win()
    return _acquire_posix()


def _acquire_posix() -> IO[str] | None:
    import fcntl

    lock_dir = Path(user_runtime_dir("dicton"))
    lock_dir.mkdir(parents=True, exist_ok=True)
    fh = open(lock_dir / "dicton.lock", "w")  # noqa: SIM115 — handle kept for lock lifetime
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        fh.close()
        return None
    fh.write(str(__import__("os").getpid()))
    fh.flush()
    return fh


def _acquire_win() -> IO[str] | None:
    import msvcrt

    lock_dir = Path(user_runtime_dir("dicton"))
    lock_dir.mkdir(parents=True, exist_ok=True)
    fh = open(lock_dir / "dicton.lock", "w")  # noqa: SIM115 — handle kept for lock lifetime
    try:
        msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        fh.close()
        return None
    return fh
