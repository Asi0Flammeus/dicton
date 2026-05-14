"""Groq cleanup LLM call."""

from __future__ import annotations

from .config import CLEANUP_MODELS
from .stt import GroqClient

SYSTEM_PROMPT = """Tu nettoies une dictée vocale française.
Corrige ponctuation, accents, accords évidents et capitalisation.
Ne traduis pas. Ne reformule pas au-delà des erreurs de dictée.
Retourne uniquement le texte final."""


async def cleanup_text(client: GroqClient, text: str, model: str) -> str:
    if not text.strip():
        return ""
    if model not in CLEANUP_MODELS:
        raise ValueError(f"Unsupported cleanup model: {model}")
    payload = {
        "model": model,
        "temperature": 0,
        "max_tokens": 1024,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
    }
    response = await client.client.post("/chat/completions", json=payload)
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]
    return str(content).strip()
