from dicton.stats import DictationStat, append_stat, summarize


def test_stats_summary_math(tmp_path) -> None:
    path = tmp_path / "stats.jsonl"
    append_stat(
        DictationStat(chars=350, audio_s=30, latency_ms=700, chunks=2, cleanup_model="m"), path
    )
    append_stat(
        DictationStat(chars=175, audio_s=15, latency_ms=900, chunks=1, cleanup_model="m"), path
    )
    summary = summarize(path)
    assert summary["dictations"] == 2
    assert summary["chars"] == 525
    assert summary["latency_ms_avg"] == 800
    assert summary["time_saved_min"] == 2.2
