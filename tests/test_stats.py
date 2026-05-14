"""Stats: append + summarise math."""

from __future__ import annotations

from pathlib import Path

from dicton import stats


def test_summarise_empty(tmp_path: Path) -> None:
    s = stats.summarise(tmp_path / "stats.jsonl")
    assert s.count == 0
    assert s.total_chars == 0


def test_summarise_aggregates(tmp_path: Path) -> None:
    p = tmp_path / "stats.jsonl"
    stats.record(
        stats.Dictation(
            ts="2026-05-14T12:00:00+00:00",
            duration_s=10.0,
            chars=200,
            chunks=2,
            recording_ms=10000,
            process_ms=1200,
            stt_ms=700,
            cleanup_ms=350,
            model="m",
        ),
        p,
    )
    stats.record(
        stats.Dictation(
            ts="2026-05-14T12:01:00+00:00",
            duration_s=20.0,
            chars=400,
            chunks=3,
            recording_ms=20000,
            process_ms=1800,
            stt_ms=1200,
            cleanup_ms=400,
            model="m",
        ),
        p,
    )
    s = stats.summarise(p)
    assert s.count == 2
    assert s.total_chars == 600
    assert s.total_audio_s == 30.0
    assert s.avg_recording_ms == 15000.0
    assert s.avg_process_ms == 1500.0
    # 600 chars / 210 cpm = ~2.86 min; audio 0.5 min → saved ~2.36 min
    assert 2.0 < s.typing_saved_min < 3.0


def test_summarise_backward_compat_old_e2e_rows(tmp_path: Path) -> None:
    """Pre-split rows had only `e2e_ms` (= recording + process). The summary
    should fall back to splitting it using `duration_s` for recording."""
    import json

    p = tmp_path / "stats.jsonl"
    p.write_text(
        json.dumps(
            {
                "ts": "2026-01-01T00:00:00+00:00",
                "duration_s": 5.0,
                "chars": 100,
                "chunks": 1,
                "e2e_ms": 5800,
                "stt_ms": 400,
                "cleanup_ms": 200,
                "model": "m",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    s = stats.summarise(p)
    assert s.count == 1
    assert s.avg_recording_ms == 5000.0
    assert s.avg_process_ms == 800.0
