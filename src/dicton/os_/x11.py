"""Process-global X11 setup. Linux/X11 only; a no-op everywhere else.

The daemon talks to the X server from two threads at once: pynput's
``keyboard.Listener`` (X11 backend) keeps a long-lived Xlib connection on a
background thread, while pygame/SDL drives ``libX11`` on the main thread for
the visualizer. ``libX11`` is **not** thread-safe unless ``XInitThreads()`` is
called once, before the first X connection is opened — otherwise the two
threads race over the shared client state, corrupt it, and the process dies
with SIGSEGV (``status=11``). See the long comment in ``visualizer.py`` for the
symptom history; this is the root-cause guard that makes the whole process
safe rather than just the visualizer's own xlib connection.
"""

from __future__ import annotations

import ctypes
import logging
import os
import sys

log = logging.getLogger("dicton")


def init_threads() -> None:
    """Enable libX11 thread-safety. Must run before any X connection.

    Call this at the very start of the daemon, before ``Pipeline.start()``
    (which opens pynput's X connection) and before the visualizer's
    ``pygame.init()`` (which opens SDL's). Safe to call when X is absent: it
    returns immediately on non-Linux, headless, or Wayland-only sessions.
    """
    if not (sys.platform.startswith("linux") and os.environ.get("DISPLAY")):
        return
    try:
        xlib = ctypes.cdll.LoadLibrary("libX11.so.6")
    except OSError:
        log.debug("libX11 not available; skipping XInitThreads()", exc_info=True)
        return
    if xlib.XInitThreads() == 0:
        log.warning("XInitThreads() returned 0 — X11 thread-safety not enabled")
