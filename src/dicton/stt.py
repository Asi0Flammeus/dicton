"""Groq Whisper STT over direct HTTP."""

from __future__ import annotations

import httpx

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
STT_MODEL = "whisper-large-v3-turbo"


class GroqClient:
    """Shared HTTP/2 client for STT and cleanup calls."""

    def __init__(self, api_key: str, timeout: float = 30.0) -> None:
        if not api_key:
            raise ValueError("Groq API key is required")
        self.api_key = api_key
        self.client = httpx.AsyncClient(
            base_url=GROQ_BASE_URL,
            http2=True,
            timeout=timeout,
            headers={"Authorization": f"Bearer {api_key}"},
        )

    async def prewarm(self) -> None:
        try:
            await self.client.get("/models", timeout=5.0)
        except httpx.HTTPError:
            pass

    async def close(self) -> None:
        await self.client.aclose()


async def transcribe(client: GroqClient, wav_bytes: bytes) -> str:
    files = {"file": ("chunk.wav", wav_bytes, "audio/wav")}
    data = {"model": STT_MODEL, "language": "fr", "response_format": "json"}
    response = await client.client.post("/audio/transcriptions", data=data, files=files)
    response.raise_for_status()
    return str(response.json().get("text", "")).strip()
