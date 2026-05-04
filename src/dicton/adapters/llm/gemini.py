"""Gemini LLM provider."""

from __future__ import annotations

import logging
import os
import threading

from .provider import LLMProvider

# Pinned in code; GEMINI_MODEL env var is intentionally ignored.
DEFAULT_GEMINI_MODEL = "gemini-flash-lite-latest"

_KEEPALIVE_EXPIRY_S = 300.0
_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com"

logger = logging.getLogger(__name__)


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
        self._model = model or DEFAULT_GEMINI_MODEL
        self._timeout = timeout if timeout is not None else float(os.getenv("API_TIMEOUT", "30"))
        self._debug = debug if debug is not None else os.getenv("DEBUG", "false").lower() == "true"
        self._client = None
        self._http_client = None  # httpx.Client backing the SDK; pooled.

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

    def _build_http_client(self):
        """Create a pooled httpx.Client for the genai SDK."""
        try:
            import httpx
        except ImportError:
            return None
        limits = httpx.Limits(
            max_keepalive_connections=1,
            max_connections=2,
            keepalive_expiry=_KEEPALIVE_EXPIRY_S,
        )
        timeout = httpx.Timeout(self._timeout)
        return httpx.Client(limits=limits, timeout=timeout)

    def _get_client(self):
        if self._client is not None:
            return self._client
        if not self._api_key:
            return None
        try:
            from google import genai
            from google.genai import types

            self._http_client = self._build_http_client()
            http_options = None
            if self._http_client is not None:
                http_options = types.HttpOptions(
                    httpx_client=self._http_client,
                    timeout=int(self._timeout * 1000),
                )
            self._client = genai.Client(api_key=self._api_key, http_options=http_options)
            return self._client
        except ImportError:
            return None

    def prewarm(self) -> None:
        """Best-effort: open one warm socket to the Gemini API.

        Spawns a daemon thread that issues a cheap GET against the API base URL
        through the pooled httpx client. The complete() call moments later
        reuses that socket and skips the TCP+TLS handshake. Silent on any
        error.
        """
        if self._http_client is None:
            self._get_client()
        if self._http_client is None:
            return

        def _warm() -> None:
            try:
                self._http_client.get(_GEMINI_BASE_URL + "/", timeout=5.0)
            except Exception as exc:
                logger.debug("gemini prewarm failed: %s", exc)

        threading.Thread(target=_warm, daemon=True).start()

    def complete(self, prompt: str, *, model: str | None = None) -> str | None:
        client = self._get_client()
        if client is None:
            return None

        try:
            from google.genai import types

            response = client.models.generate_content(
                model=model or self._model,
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
        if self._http_client is not None:
            try:
                self._http_client.close()
            except Exception:
                pass
            self._http_client = None
