"""Gemini LLM provider."""

from __future__ import annotations

from .provider import LLMProvider


class GeminiLLMProvider(LLMProvider):
    """Google Gemini LLM provider."""

    def __init__(self) -> None:
        self._client = None

    @property
    def name(self) -> str:
        return "gemini"

    def is_available(self) -> bool:
        from ...shared.config import config

        if not config.GEMINI_API_KEY:
            return False
        try:
            from google import genai  # noqa: F401

            return True
        except ImportError:
            return False

    def _get_client(self):
        if self._client is not None:
            return self._client
        from ...shared.config import config

        if not config.GEMINI_API_KEY:
            return None
        try:
            from google import genai

            self._client = genai.Client(api_key=config.GEMINI_API_KEY)
            return self._client
        except ImportError:
            return None

    def complete(self, prompt: str) -> str | None:
        client = self._get_client()
        if client is None:
            return None
        from ...shared.config import config

        try:
            from google.genai import types

            response = client.models.generate_content(
                model=config.GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    http_options=types.HttpOptions(timeout=int(config.API_TIMEOUT * 1000)),
                ),
            )
            if response.text:
                return response.text.strip()
            return None
        except Exception as e:
            if config.DEBUG:
                print(f"Gemini error: {e}")
            raise

    def cleanup(self) -> None:
        self._client = None
