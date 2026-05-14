import pytest

from dicton.config import Config
from dicton.pipeline import Pipeline


@pytest.mark.asyncio
async def test_pipeline_mocked(monkeypatch) -> None:
    async def fake_transcribe(_client, _wav):
        return "bonjour monde"

    async def fake_cleanup(_client, text, _model):
        return text.capitalize() + "."

    class Client:
        def __init__(self, _key):
            pass

        async def prewarm(self):
            pass

        async def close(self):
            pass

    pasted = []
    monkeypatch.setattr("dicton.pipeline.GroqClient", Client)
    monkeypatch.setattr("dicton.pipeline.transcribe", fake_transcribe)
    monkeypatch.setattr("dicton.pipeline.cleanup_text", fake_cleanup)
    monkeypatch.setattr("dicton.pipeline.paste", pasted.append)
    monkeypatch.setattr("dicton.pipeline.append_stat", lambda stat: None)
    p = Pipeline(Config(groq_api_key="k", min_chunk_s=10, silence_window_s=0.1, overlap_s=0))
    await p.start_recording()
    await p.feed_audio((10000).to_bytes(2, "little", signed=True) * 800)
    await p.feed_audio((0).to_bytes(2, "little", signed=True) * 800)
    await p.feed_audio((0).to_bytes(2, "little", signed=True) * 800)
    result = await p.stop_recording()
    assert result == "Bonjour monde."
    assert pasted == ["Bonjour monde."]
