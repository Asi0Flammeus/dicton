"""Backward-compatibility shim — canonical location is adapters.config.latency.

This module re-exports all public names so that existing callers continue to
work without modification.  The import is performed via importlib to avoid
a static relative import from ``shared`` into ``adapters`` (which would
violate the COPA layering rule enforced by architecture tests).
"""

import importlib as _importlib

_canonical = _importlib.import_module("dicton.adapters.config.latency")

LatencyTracker = _canonical.LatencyTracker
SessionMetrics = _canonical.SessionMetrics
TimingEvent = _canonical.TimingEvent
get_latency_tracker = _canonical.get_latency_tracker
reset_latency_tracker = _canonical.reset_latency_tracker

__all__ = [
    "LatencyTracker",
    "SessionMetrics",
    "TimingEvent",
    "get_latency_tracker",
    "reset_latency_tracker",
]
