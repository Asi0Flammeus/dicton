"""STT + cleanup HTTP calls, mocked via respx."""

from __future__ import annotations

import httpx
import pytest
import respx

from dicton.cleanup import cleanup
from dicton.stt import GROQ_BASE, Segment, is_hallucination, transcribe


def _seg(text: str, *, no_speech=0.0, logprob=-0.7, compr=0.7) -> Segment:
    return Segment(
        text=text, no_speech_prob=no_speech, avg_logprob=logprob, compression_ratio=compr
    )


@pytest.mark.asyncio
@respx.mock
async def test_transcribe_parses_segments() -> None:
    respx.post(f"{GROQ_BASE}/audio/transcriptions").mock(
        return_value=httpx.Response(
            200,
            json={
                "text": "bonjour monde",
                "segments": [
                    {
                        "text": " bonjour monde",
                        "no_speech_prob": 0.0,
                        "avg_logprob": -0.7,
                        "compression_ratio": 0.7,
                    }
                ],
            },
        )
    )
    async with httpx.AsyncClient(http2=False) as c:
        result = await transcribe(c, b"WAVE", api_key="sk-test")
    assert result.clean_text() == "bonjour monde"
    assert result.dropped == 0


@pytest.mark.asyncio
@respx.mock
async def test_transcribe_drops_hallucinated_segment() -> None:
    respx.post(f"{GROQ_BASE}/audio/transcriptions").mock(
        return_value=httpx.Response(
            200,
            json={
                "text": "x",
                "segments": [
                    {
                        "text": " on se voit demain",
                        "no_speech_prob": 0.01,
                        "avg_logprob": -0.6,
                        "compression_ratio": 0.8,
                    },
                    {
                        "text": " Sous-titrage Société Radio-Canada",
                        "no_speech_prob": 0.92,
                        "avg_logprob": -0.9,
                        "compression_ratio": 1.1,
                    },
                ],
            },
        )
    )
    async with httpx.AsyncClient(http2=False) as c:
        result = await transcribe(c, b"WAVE", api_key="sk-test")
    assert result.clean_text() == "on se voit demain"
    assert result.dropped == 1


def test_transcribe_no_segments_keeps_top_level_text() -> None:
    from dicton.stt import _parse_transcript

    t = _parse_transcript({"text": "ok", "segments": []})
    assert t.clean_text() == "ok"


def test_is_hallucination_rules() -> None:
    assert not is_hallucination(_seg("vrai texte"))
    assert is_hallucination(_seg("silence", no_speech=0.85))  # near-certain silence
    assert is_hallucination(_seg("faible", no_speech=0.65, logprob=-0.9))  # silence + weak
    assert is_hallucination(_seg("merci merci merci", compr=3.0))  # repetition
    assert is_hallucination(_seg("garbage", logprob=-1.4))  # very low confidence


@pytest.mark.asyncio
@respx.mock
async def test_cleanup_returns_cleaned_message() -> None:
    respx.post(f"{GROQ_BASE}/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={"choices": [{"message": {"content": "Bonjour monde."}}]},
        )
    )
    async with httpx.AsyncClient(http2=False) as c:
        out = await cleanup(c, "bonjour monde", api_key="sk-test", model="gpt-oss-20b")
    assert out == "Bonjour monde."


@pytest.mark.asyncio
@respx.mock
async def test_cleanup_falls_back_to_raw_on_error() -> None:
    respx.post(f"{GROQ_BASE}/chat/completions").mock(return_value=httpx.Response(500))
    async with httpx.AsyncClient(http2=False) as c:
        out = await cleanup(c, "le brut", api_key="sk-test", model="m")
    assert out == "le brut"
