"""Daemon entrypoint — singleton lock + Pipeline + main-thread pygame loop."""

from __future__ import annotations

import logging
import time

from . import singleton
from .config import Config
from .pipeline import Pipeline
from .visualizer import Visualizer

log = logging.getLogger("dicton")


def run(cfg: Config) -> None:
    """Blocking entrypoint. Acquires the singleton lock, starts the pipeline,
    then runs the pygame loop on the main thread (required on macOS)."""
    lock = singleton.acquire()
    if lock is None:
        log.error("Another dicton instance is already running. Refusing to start.")
        return

    viz = Visualizer() if cfg.visualizer else None
    pipe = Pipeline(cfg, viz=viz)
    pipe.start()
    try:
        if viz is not None:
            # viz.run() owns the main thread (required on macOS) and returns
            # on stop, on window close, or after it gives up on a wedged
            # display. If the pipeline is still live when it returns, the
            # visualizer merely died — keep serving dictations (record +
            # paste) without the animation rather than tearing down the daemon.
            viz.run()
        while not pipe._stop.is_set():
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        pipe.stop()
        lock.close()
