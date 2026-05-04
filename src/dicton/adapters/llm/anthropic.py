"""Anthropic LLM provider."""

from __future__ import annotations

import os

from .provider import LLMProvider


class AnthropicLLMProvider(LLMProvider):
    """Anthropic Claude LLM provider."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
        debug: bool | None = None,
    ) -> None:
        self._api_key = api_key if api_key is not None else os.getenv("ANTHROPIC_API_KEY", "")
        self._model = model or os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
        self._timeout = timeout if timeout is not None else float(os.getenv("API_TIMEOUT", "30"))
        self._debug = debug if debug is not None else os.getenv("DEBUG", "false").lower() == "true"
        self._client = None

    @property
    def name(self) -> str:
        return "anthropic"

    def is_available(self) -> bool:
        if not self._api_key:
            return False
        try:
            import anthropic  # noqa: F401

            return True
        except ImportError:
            return False

    def _get_client(self):
        if self._client is not None:
            return self._client
        if not self._api_key:
            return None
        try:
            import anthropic

            self._client = anthropic.Anthropic(api_key=self._api_key)
            return self._client
        except ImportError:
            return None

    def complete(self, prompt: str, *, model: str | None = None) -> str | None:
        client = self._get_client()
        if client is None:
            return None

        try:
            message = client.messages.create(
                model=model or self._model,
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
                timeout=self._timeout,
            )
            if message.content and len(message.content) > 0:
                return message.content[0].text.strip()
            return None
        except Exception as e:
            if self._debug:
                print(f"Anthropic error: {e}")
            raise

    def cleanup(self) -> None:
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None
