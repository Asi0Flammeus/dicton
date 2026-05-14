"""Groq Whisper STT via direct httpx call.

Shares the AsyncClient with `cleanup` so STT + cleanup go through the same
TCP+TLS+HTTP/2 connection to api.groq.com.
"""

from __future__ import annotations

import contextlib
import io
import wave

import httpx
import numpy as np

GROQ_BASE = "https://api.groq.com/openai/v1"


def pcm16_to_wav(pcm: np.ndarray, sample_rate: int) -> bytes:
    """Encode mono int16 PCM samples as a WAV byte string."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm.astype(np.int16).tobytes())
    return buf.getvalue()


async def transcribe(
    client: httpx.AsyncClient,
    wav_bytes: bytes,
    *,
    api_key: str,
    model: str = "whisper-large-v3-turbo",
    language: str = "fr",
    timeout: float = 30.0,
) -> str:
    """POST audio to Groq Whisper and return the raw transcript."""
    files = {"file": ("audio.wav", wav_bytes, "audio/wav")}
    data = {
        "model": model,
        "language": language,
        "response_format": "text",
        "temperature": "0",
    }
    headers = {"Authorization": f"Bearer {api_key}"}
    r = await client.post(
        f"{GROQ_BASE}/audio/transcriptions",
        headers=headers,
        files=files,
        data=data,
        timeout=timeout,
    )
    r.raise_for_status()
    return r.text.strip()


async def prewarm(client: httpx.AsyncClient, *, api_key: str) -> None:
    """Warm the TLS + HTTP/2 connection to api.groq.com with a cheap GET."""
    with contextlib.suppress(httpx.HTTPError):
        await client.get(
            f"{GROQ_BASE}/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=5.0,
        )
