"""Latency tracking for Dicton - measure and log pipeline performance

This module provides timing instrumentation for key pipeline stages:
- Recording start/stop
- Audio capture duration
- STT processing time
- Text output time
"""

import json
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from statistics import mean, median, quantiles
from typing import Any

from .config import config


@dataclass
class TimingEvent:
    """A single timing measurement"""

    stage: str
    start_time: float
    end_time: float
    duration_ms: float = field(init=False)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        self.duration_ms = (self.end_time - self.start_time) * 1000


@dataclass
class SessionMetrics:
    """Aggregated metrics for a dictation session"""

    session_id: str
    start_time: float
    end_time: float | None = None
    events: list[TimingEvent] = field(default_factory=list)

    def total_duration_ms(self) -> float:
        """Total session duration in milliseconds"""
        end = self.end_time or time.time()
        return (end - self.start_time) * 1000

    def stage_durations(self) -> dict[str, list[float]]:
        """Get durations grouped by stage"""
        durations: dict[str, list[float]] = defaultdict(list)
        for event in self.events:
            durations[event.stage].append(event.duration_ms)
        return dict(durations)


class LatencyTracker:
    """Track and log latency metrics for the dictation pipeline

    Usage:
        tracker = get_latency_tracker()
        tracker.start_session()

        with tracker.measure("audio_capture"):
            # ... capture audio ...

        with tracker.measure("stt_processing"):
            # ... transcribe ...

        tracker.end_session()
        tracker.print_summary()
    """

    def __init__(self, log_path: Path | str | None = None, enabled: bool = True):
        """Initialize the latency tracker.

        Args:
            log_path: Path to latency log file. If None, uses default location.
            enabled: If False, all tracking is disabled (no-op).
        """
        self.enabled = enabled
        self._sessions: list[SessionMetrics] = []
        self._current_session: SessionMetrics | None = None
        self._stage_starts: dict[str, float] = {}

        # Default log location
        if log_path is None:
            self.log_path = Path.home() / ".config" / "dicton" / "latency.log"
        else:
            self.log_path = Path(log_path)

    def start_session(self, session_id: str | None = None) -> str:
        """Start a new timing session.

        Args:
            session_id: Optional custom session ID. If None, uses timestamp.

        Returns:
            The session ID.
        """
        if not self.enabled:
            return ""

        if session_id is None:
            session_id = f"session_{int(time.time() * 1000)}"

        self._current_session = SessionMetrics(
            session_id=session_id,
            start_time=time.time(),
        )
        self._sessions.append(self._current_session)
        return session_id

    def end_session(self) -> SessionMetrics | None:
        """End the current timing session.

        Returns:
            The completed session metrics, or None if no session was active.
        """
        if not self.enabled or self._current_session is None:
            return None

        self._current_session.end_time = time.time()
        session = self._current_session
        self._current_session = None

        # Log to file
        self._log_session(session)

        return session

    def start_stage(self, stage: str) -> None:
        """Start timing a stage (manual start/stop).

        Args:
            stage: Name of the pipeline stage.
        """
        if not self.enabled:
            return
        self._stage_starts[stage] = time.time()

    def end_stage(self, stage: str, **metadata: Any) -> TimingEvent | None:
        """End timing a stage.

        Args:
            stage: Name of the pipeline stage.
            **metadata: Additional metadata to attach to the event.

        Returns:
            The timing event, or None if stage wasn't started.
        """
        if not self.enabled:
            return None

        start_time = self._stage_starts.pop(stage, None)
        if start_time is None:
            return None

        end_time = time.time()
        event = TimingEvent(
            stage=stage,
            start_time=start_time,
            end_time=end_time,
            metadata=metadata,
        )

        if self._current_session:
            self._current_session.events.append(event)

        return event

    class _MeasureContext:
        """Context manager for measuring a stage"""

        def __init__(self, tracker: "LatencyTracker", stage: str, **metadata: Any):
            self.tracker = tracker
            self.stage = stage
            self.metadata = metadata

        def __enter__(self):
            self.tracker.start_stage(self.stage)
            return self

        def __exit__(self, *args):
            self.tracker.end_stage(self.stage, **self.metadata)

    def measure(self, stage: str, **metadata: Any) -> _MeasureContext:
        """Context manager for measuring a stage.

        Usage:
            with tracker.measure("stt_processing"):
                result = transcribe(audio)
        """
        return self._MeasureContext(self, stage, **metadata)

    def _log_session(self, session: SessionMetrics) -> None:
        """Log session metrics to file."""
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)

            log_entry = {
                "session_id": session.session_id,
                "start_time": session.start_time,
                "end_time": session.end_time,
                "total_ms": session.total_duration_ms(),
                "stages": [
                    {
                        "stage": e.stage,
                        "duration_ms": e.duration_ms,
                        "metadata": e.metadata,
                    }
                    for e in session.events
                ],
            }

            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry) + "\n")

        except OSError as e:
            if config.DEBUG:
                print(f"⚠ Failed to log latency: {e}")

    def get_statistics(self, last_n_sessions: int | None = None) -> dict[str, dict[str, float]]:
        """Get latency statistics across sessions.

        Args:
            last_n_sessions: Only consider the last N sessions. None means all.

        Returns:
            Dict mapping stage names to statistics (p50, p95, p99, mean).
        """
        sessions = self._sessions
        if last_n_sessions is not None:
            sessions = sessions[-last_n_sessions:]

        # Collect all durations by stage
        all_durations: dict[str, list[float]] = defaultdict(list)
        for session in sessions:
            for event in session.events:
                all_durations[event.stage].append(event.duration_ms)

        # Calculate statistics
        stats: dict[str, dict[str, float]] = {}
        for stage, durations in all_durations.items():
            if len(durations) < 2:
                stats[stage] = {
                    "count": len(durations),
                    "mean": durations[0] if durations else 0,
                    "p50": durations[0] if durations else 0,
                    "p95": durations[0] if durations else 0,
                    "p99": durations[0] if durations else 0,
                }
            else:
                sorted_d = sorted(durations)
                try:
                    q = quantiles(sorted_d, n=100)
                    p50 = q[49]
                    p95 = q[94]
                    p99 = q[98]
                except Exception:
                    # Fallback for small sample sizes
                    p50 = median(sorted_d)
                    p95 = (
                        sorted_d[int(len(sorted_d) * 0.95)] if len(sorted_d) >= 20 else sorted_d[-1]
                    )
                    p99 = (
                        sorted_d[int(len(sorted_d) * 0.99)]
                        if len(sorted_d) >= 100
                        else sorted_d[-1]
                    )

                stats[stage] = {
                    "count": len(durations),
                    "mean": mean(durations),
                    "p50": p50,
                    "p95": p95,
                    "p99": p99,
                    "min": min(durations),
                    "max": max(durations),
                }

        return stats

    def print_summary(self, last_n_sessions: int | None = None) -> None:
        """Print a summary of latency statistics."""
        stats = self.get_statistics(last_n_sessions)

        if not stats:
            print("No latency data collected.")
            return

        print("\n📊 Latency Summary")
        print("=" * 60)
        print(f"{'Stage':<20} {'Count':>6} {'P50':>8} {'P95':>8} {'P99':>8}")
        print("-" * 60)

        total_p50 = 0.0
        for stage, s in stats.items():
            print(
                f"{stage:<20} {s['count']:>6} {s['p50']:>7.1f}ms {s['p95']:>7.1f}ms {s['p99']:>7.1f}ms"
            )
            total_p50 += s["p50"]

        print("-" * 60)
        print(f"{'Total (sum P50)':<20} {'':<6} {total_p50:>7.1f}ms")
        print("=" * 60)

    def load_from_log(self) -> int:
        """Load historical data from log file.

        Returns:
            Number of sessions loaded.
        """
        if not self.log_path.exists():
            return 0

        count = 0
        try:
            with open(self.log_path, encoding="utf-8") as f:
                for line in f:
                    try:
                        data = json.loads(line.strip())
                        session = SessionMetrics(
                            session_id=data["session_id"],
                            start_time=data["start_time"],
                            end_time=data.get("end_time"),
                        )
                        for stage_data in data.get("stages", []):
                            # Reconstruct timing events
                            duration_s = stage_data["duration_ms"] / 1000
                            event = TimingEvent(
                                stage=stage_data["stage"],
                                start_time=0,  # Not preserved in log
                                end_time=duration_s,
                                metadata=stage_data.get("metadata", {}),
                            )
                            event.duration_ms = stage_data["duration_ms"]
                            session.events.append(event)
                        self._sessions.append(session)
                        count += 1
                    except (json.JSONDecodeError, KeyError):
                        continue
        except OSError:
            pass

        return count

    def clear_log(self) -> None:
        """Clear the latency log file."""
        try:
            if self.log_path.exists():
                self.log_path.unlink()
        except OSError:
            pass

    def clear_memory(self) -> None:
        """Clear in-memory session data."""
        self._sessions.clear()
        self._current_session = None


# Global tracker instance
_latency_tracker: LatencyTracker | None = None


def get_latency_tracker() -> LatencyTracker:
    """Get the global latency tracker instance."""
    global _latency_tracker
    if _latency_tracker is None:
        _latency_tracker = LatencyTracker(enabled=config.DEBUG)
    return _latency_tracker


def reset_latency_tracker() -> None:
    """Reset the global latency tracker (for testing)."""
    global _latency_tracker
    _latency_tracker = None
