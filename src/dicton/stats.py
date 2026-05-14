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
    e2e_ms: int
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
    avg_e2e_ms: float


def summarise(path: Path = STATS_PATH) -> Summary:
    if not path.exists():
        return Summary(0, 0, 0.0, 0.0, 0.0)
    count = 0
    chars = 0
    audio = 0.0
    e2e_sum = 0
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
            audio += float(d.get("duration_s", 0.0))
            e2e_sum += int(d.get("e2e_ms", 0))
    typing_min = (chars / TYPING_CPM) - (audio / 60.0)
    return Summary(
        count=count,
        total_chars=chars,
        total_audio_s=audio,
        typing_saved_min=max(typing_min, 0.0),
        avg_e2e_ms=(e2e_sum / count) if count else 0.0,
    )
