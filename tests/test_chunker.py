from dicton.chunker import Chunker, ChunkSettings


def frame(amp: int, samples: int = 800) -> bytes:
    return (amp.to_bytes(2, "little", signed=True)) * samples


def test_silence_cut_after_min_duration() -> None:
    c = Chunker(ChunkSettings(min_chunk_s=0.1, silence_window_s=0.1, frame_ms=50, overlap_s=0))
    assert c.feed(frame(10000)) is None
    assert c.feed(frame(0)) is None
    wav = c.feed(frame(0))
    assert wav and wav.startswith(b"RIFF")


def test_max_cut() -> None:
    c = Chunker(ChunkSettings(max_chunk_s=0.1, frame_ms=50, overlap_s=0))
    assert c.feed(frame(10000)) is None
    assert c.feed(frame(10000)) and c.boundary == 2


def test_overlap_rewinds_boundary() -> None:
    c = Chunker(ChunkSettings(max_chunk_s=0.15, frame_ms=50, overlap_s=0.05))
    c.feed(frame(10000))
    c.feed(frame(10000))
    c.feed(frame(10000))
    assert c.boundary == 2
