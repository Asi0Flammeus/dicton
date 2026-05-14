"""Local JSONL stats — append per-dictation, summarise on demand."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from .config import STATS_PATH

# Average human typing throughput, French (chars/min): ~210
TYPING_CPM = 210.0


@dataclass
class Dictation:
    ts: str
    duration_s: float
    chars: int
    chunks: int
    recording_ms: int  # hotkey-on → hotkey-off (user speaking)
    process_ms: int  # hotkey-off → text pasted (server-side latency)
    stt_ms: int
    cleanup_ms: int
    model: str


def record(d: Dictation, path: Path = STATS_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(d)) + "\n")


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass
class Summary:
    count: int
    total_chars: int
    total_audio_s: float
    typing_saved_min: float
    avg_recording_ms: float
    avg_process_ms: float


def summarise(path: Path = STATS_PATH) -> Summary:
    if not path.exists():
        return Summary(0, 0, 0.0, 0.0, 0.0, 0.0)
    count = 0
    chars = 0
    audio = 0.0
    rec_sum = 0
    proc_sum = 0
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            count += 1
            chars += int(d.get("chars", 0))
            duration_s = float(d.get("duration_s", 0.0))
            audio += duration_s
            # Backward compat: rows written before the split stored the full
            # session timing as ``e2e_ms``. Use ``duration_s`` for recording
            # and the remainder for process when ``recording_ms`` is absent.
            if "recording_ms" in d:
                rec_sum += int(d["recording_ms"])
                proc_sum += int(d.get("process_ms", 0))
            else:
                rec_sum += int(duration_s * 1000)
                e2e = int(d.get("e2e_ms", 0))
                proc_sum += max(0, e2e - int(duration_s * 1000))
    typing_min = (chars / TYPING_CPM) - (audio / 60.0)
    return Summary(
        count=count,
        total_chars=chars,
        total_audio_s=audio,
        typing_saved_min=max(typing_min, 0.0),
        avg_recording_ms=(rec_sum / count) if count else 0.0,
        avg_process_ms=(proc_sum / count) if count else 0.0,
    )
