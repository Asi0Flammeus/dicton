"""Daemon entrypoint — singleton lock + Pipeline + main-thread pygame loop."""

from __future__ import annotations

import logging
import time

from .config import Config
from .os_ import single_instance as singleton
from .os_ import x11

log = logging.getLogger("dicton")


def run(cfg: Config) -> None:
    """Blocking entrypoint. Acquires the singleton lock, starts the pipeline,
    then runs the pygame loop on the main thread (required on macOS)."""
    # Must precede every X connection. Keep Pipeline/Visualizer imports below:
    # pipeline imports pynput.keyboard at module import time, and pynput's X11
    # backend opens an X connection immediately. Importing it before
    # XInitThreads() makes the guard too late and leaves the SIGSEGV race alive.
    x11.init_threads()
    from .pipeline import Pipeline
    from .visualizer import Visualizer

    lock = singleton.acquire()
    if lock is None:
        log.error("Another dicton instance is already running. Refusing to start.")
        return

    viz = Visualizer() if cfg.visualizer else None
    pipe = Pipeline(cfg, viz=viz)
    pipe.start()
    try:
        if viz is not None:
            # viz.run() owns the main thread (required on macOS). It returns
            # on a shutdown request (SDL QUIT / SIGTERM → quit_requested) OR
            # after the visualizer crashed/gave up on a wedged display. Only
            # in the latter case do we keep serving dictations (record +
            # paste) without animation; a real shutdown must fall through to
            # the finally so systemd's `restart` doesn't hang.
            viz.run()
            if not viz.quit_requested:
                while not pipe._stop.is_set():
                    time.sleep(0.5)
        else:
            while not pipe._stop.is_set():
                time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        pipe.stop()
        lock.close()
