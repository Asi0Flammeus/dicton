"""Prevent multiple Dicton instances from running simultaneously."""

from __future__ import annotations

import os
import sys


def acquire_instance_lock() -> object | None:
    """Acquire an exclusive lock to ensure only one Dicton instance runs.

    Returns the lock file object (must be kept alive) or None on failure.
    The lock is automatically released when the process exits, even on crash.
    """
    if sys.platform == "win32":
        return _acquire_win32()
    return _acquire_posix()


def _get_lock_path() -> str:
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("TEMP", ".")
        return os.path.join(base, "dicton.lock")

    # Prefer XDG runtime dir (/run/user/<uid>/) — tmpfs, auto-cleaned
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
    if runtime_dir:
        return os.path.join(runtime_dir, "dicton.lock")

    # Fallback to /tmp
    return f"/tmp/dicton-{os.getuid()}.lock"


def _acquire_posix() -> object | None:
    import fcntl

    lock_path = _get_lock_path()
    try:
        lock_file = open(lock_path, "w")
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        lock_file.write(str(os.getpid()))
        lock_file.flush()
        return lock_file
    except OSError:
        return None


def _acquire_win32() -> object | None:
    import msvcrt

    lock_path = _get_lock_path()
    try:
        lock_file = open(lock_path, "w")
        msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
        lock_file.write(str(os.getpid()))
        lock_file.flush()
        return lock_file
    except OSError:
        return None
