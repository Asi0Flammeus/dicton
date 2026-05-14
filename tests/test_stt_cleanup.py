"""STT + cleanup HTTP calls, mocked via respx."""

from __future__ import annotations

import httpx
import pytest
import respx

from dicton.cleanup import cleanup
from dicton.stt import GROQ_BASE, transcribe


@pytest.mark.asyncio
@respx.mock
async def test_transcribe_returns_text_body() -> None:
    respx.post(f"{GROQ_BASE}/audio/transcriptions").mock(
        return_value=httpx.Response(200, text="bonjour monde")
    )
    async with httpx.AsyncClient(http2=False) as c:
        result = await transcribe(c, b"WAVE", api_key="sk-test")
    assert result == "bonjour monde"


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
