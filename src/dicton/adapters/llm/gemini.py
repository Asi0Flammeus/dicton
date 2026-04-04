"""Gemini LLM provider."""

from __future__ import annotations

import os

from .provider import LLMProvider


class GeminiLLMProvider(LLMProvider):
    """Google Gemini LLM provider."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
        debug: bool | None = None,
    ) -> None:
        self._api_key = api_key if api_key is not None else os.getenv("GEMINI_API_KEY", "")
        self._model = model or os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
        self._timeout = timeout if timeout is not None else float(os.getenv("API_TIMEOUT", "30"))
        self._debug = debug if debug is not None else os.getenv("DEBUG", "false").lower() == "true"
        self._client = None

    @property
    def name(self) -> str:
        return "gemini"

    def is_available(self) -> bool:
        if not self._api_key:
            return False
        try:
            from google import genai  # noqa: F401

            return True
        except ImportError:
            return False

    def _get_client(self):
        if self._client is not None:
            return self._client
        if not self._api_key:
            return None
        try:
            from google import genai

            self._client = genai.Client(api_key=self._api_key)
            return self._client
        except ImportError:
            return None

    def complete(self, prompt: str) -> str | None:
        client = self._get_client()
        if client is None:
            return None

        try:
            from google.genai import types

            response = client.models.generate_content(
                model=self._model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    http_options=types.HttpOptions(timeout=int(self._timeout * 1000)),
                ),
            )
            if response.text:
                return response.text.strip()
            return None
        except Exception as e:
            if self._debug:
                print(f"Gemini error: {e}")
            raise

    def cleanup(self) -> None:
        self._client = None
