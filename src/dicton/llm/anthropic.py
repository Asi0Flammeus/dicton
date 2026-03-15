"""Anthropic LLM provider."""

from __future__ import annotations

from .provider import LLMProvider


class AnthropicLLMProvider(LLMProvider):
    """Anthropic Claude LLM provider."""

    def __init__(self) -> None:
        self._client = None

    @property
    def name(self) -> str:
        return "anthropic"

    def is_available(self) -> bool:
        from ..config import config

        if not config.ANTHROPIC_API_KEY:
            return False
        try:
            import anthropic  # noqa: F401

            return True
        except ImportError:
            return False

    def _get_client(self):
        if self._client is not None:
            return self._client
        from ..config import config

        if not config.ANTHROPIC_API_KEY:
            return None
        try:
            import anthropic

            self._client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
            return self._client
        except ImportError:
            return None

    def complete(self, prompt: str) -> str | None:
        client = self._get_client()
        if client is None:
            return None
        from ..config import config

        try:
            message = client.messages.create(
                model=config.ANTHROPIC_MODEL,
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
                timeout=config.API_TIMEOUT,
            )
            if message.content and len(message.content) > 0:
                return message.content[0].text.strip()
            return None
        except Exception as e:
            if config.DEBUG:
                print(f"Anthropic error: {e}")
            raise

    def cleanup(self) -> None:
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None
