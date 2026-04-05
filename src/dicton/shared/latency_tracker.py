"""Backward-compat shim — canonical home is ``adapters.config.latency``."""

from ..adapters.config.latency import *  # noqa: F401,F403
from ..adapters.config.latency import (  # noqa: F401
    LatencyTracker,
    SessionMetrics,
    TimingEvent,
    get_latency_tracker,
    reset_latency_tracker,
)
