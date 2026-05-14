"""Local JSONL stats."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from platformdirs import user_data_dir

STATS_PATH = Path(user_data_dir("dicton", appauthor=False)) / "stats.jsonl"


@dataclass(slots=True)
class DictationStat:
    chars: int
    audio_s: float
    latency_ms: int
    chunks: int
    cleanup_model: str
    created_at: float = 0.0


def append_stat(stat: DictationStat, path: Path = STATS_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    stat.created_at = stat.created_at or time.time()
    with path.open("a") as fh:
        fh.write(json.dumps(asdict(stat), ensure_ascii=False) + "\n")


def summarize(path: Path = STATS_PATH) -> dict[str, float | int]:
    if not path.exists():
        return {
            "dictations": 0,
            "chars": 0,
            "audio_s": 0.0,
            "latency_ms_avg": 0,
            "time_saved_min": 0.0,
        }
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    total_chars = sum(int(r.get("chars", 0)) for r in rows)
    latencies = [int(r.get("latency_ms", 0)) for r in rows]
    # Rough typing baseline: 35 French words/min, 5 chars/word.
    time_saved_min = max(
        0.0, total_chars / 175 - sum(float(r.get("audio_s", 0)) for r in rows) / 60
    )
    return {
        "dictations": len(rows),
        "chars": total_chars,
        "audio_s": sum(float(r.get("audio_s", 0)) for r in rows),
        "latency_ms_avg": round(sum(latencies) / len(latencies)) if latencies else 0,
        "time_saved_min": round(time_saved_min, 1),
    }
