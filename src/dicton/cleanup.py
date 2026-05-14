"""Groq LLM cleanup pass — single call on the joined transcript.

The model is selected at the wizard (one of four embedded options) and stored
in TOML. Same httpx client as stt.py — same TLS handshake, same pool.
"""

from __future__ import annotations

import httpx

from .config import DEFAULT_PROMPT
from .stt import GROQ_BASE


async def cleanup(
    client: httpx.AsyncClient,
    text: str,
    *,
    api_key: str,
    model: str,
    timeout: float = 30.0,
    prompt: str = DEFAULT_PROMPT,
) -> str:
    """Send the raw transcript to Groq Chat and return the cleaned string.

    Falls back to the raw input on any error so a cleanup hiccup never costs
    the user their dictation.
    """
    if not text.strip():
        return text
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": text},
        ],
        "temperature": 0.0,
        "stream": False,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    try:
        r = await client.post(
            f"{GROQ_BASE}/chat/completions",
            headers=headers,
            json=payload,
            timeout=timeout,
        )
        r.raise_for_status()
        data = r.json()
        cleaned = data["choices"][0]["message"]["content"].strip()
        return _strip_wrapping_quotes(cleaned) or text
    except (httpx.HTTPError, KeyError, IndexError, ValueError):
        return text


def _strip_wrapping_quotes(s: str) -> str:
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ('"', "'", "«"):
        return s[1:-1].strip()
    return s
