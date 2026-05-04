"""Unit tests for the pre-output transcript cleaner."""

from __future__ import annotations

import pytest

from dicton.adapters.llm import factory as factory_module
from dicton.adapters.llm.cleaner import _build_prompt, clean_transcript
from dicton.adapters.llm.provider import LLMProvider


class _FakeProvider(LLMProvider):
    def __init__(
        self,
        *,
        provider_name: str = "gemini",
        result: str | None = "cleaned text",
        available: bool = True,
        raise_on_call: Exception | None = None,
    ) -> None:
        self._provider_name = provider_name
        self._result = result
        self._available = available
        self._raise = raise_on_call
        self.calls: list[tuple[str, str | None]] = []

    @property
    def name(self) -> str:
        return self._provider_name

    def is_available(self) -> bool:
        return self._available

    def complete(self, prompt: str, *, model: str | None = None) -> str | None:
        self.calls.append((prompt, model))
        if self._raise is not None:
            raise self._raise
        return self._result


@pytest.fixture
def patch_providers(monkeypatch):
    """Patch the cleaner with a configurable provider registry.

    Pass a ``{provider_name: _FakeProvider}`` dict; the cleaner's
    fallback order is set to the dict's key order so tests can control
    which provider is primary and which is the fallback.
    """

    def _patch(providers: dict[str, _FakeProvider]):
        monkeypatch.setattr(
            "dicton.adapters.llm.cleaner.DEFAULT_FALLBACK_ORDER",
            list(providers.keys()),
        )

        def _get(name: str, use_cache: bool = True):
            if name in providers:
                return providers[name]
            from dicton.adapters.llm.provider import NullLLMProvider

            return NullLLMProvider()

        monkeypatch.setattr("dicton.adapters.llm.cleaner.get_llm_provider", _get)
        monkeypatch.setattr("dicton.adapters.llm.cleaner._register_providers", lambda: None)
        return providers

    yield _patch
    factory_module._provider_cache.clear()


def test_happy_path_returns_provider_text(patch_providers):
    providers = patch_providers({"gemini": _FakeProvider(result="je voulais te dire bonjour.")})
    out = clean_transcript("euh, je voulais, euh, te dire bonjour")
    assert out == "je voulais te dire bonjour."
    assert providers["gemini"].calls, "provider should be called"


def test_fail_open_returns_none_when_only_provider_raises(patch_providers):
    patch_providers({"gemini": _FakeProvider(raise_on_call=RuntimeError("boom"))})
    assert clean_transcript("hello world") is None


def test_provider_unavailable_returns_none(patch_providers):
    patch_providers({"gemini": _FakeProvider(available=False)})
    assert clean_transcript("hello world") is None


def test_none_string_sentinel_propagates(patch_providers):
    patch_providers({"gemini": _FakeProvider(result="None")})
    out = clean_transcript("...")
    assert out == "None"


def test_empty_input_returns_none(patch_providers):
    providers = patch_providers({"gemini": _FakeProvider(result="should not be called")})
    assert clean_transcript("") is None
    assert providers["gemini"].calls == []


def test_prompt_embeds_critical_rules(patch_providers):
    providers = patch_providers({"gemini": _FakeProvider(result="ok")})
    clean_transcript("hello [bruit] world", language="fr")
    prompt, _model = providers["gemini"].calls[0]
    # bracket-stripping rule
    assert "[bruit]" in prompt or "bracketed" in prompt.lower()
    # filler-removal rule
    assert "filler" in prompt.lower()
    # language-preservation rule (the headline rule of the cleaner)
    assert "same language" in prompt.lower()
    assert "never translate" in prompt.lower()


def test_default_model_for_primary_provider_is_provider_specific(patch_providers):
    providers = patch_providers(
        {
            "gemini": _FakeProvider(provider_name="gemini", result="ok"),
            "anthropic": _FakeProvider(provider_name="anthropic", result="ok"),
        }
    )

    clean_transcript("hello", user_provider="gemini")
    assert providers["gemini"].calls[-1][1] == "gemini-flash-lite-latest"

    clean_transcript("hello", user_provider="anthropic")
    assert providers["anthropic"].calls[-1][1] == "claude-haiku-4-5-20251001"


def test_explicit_model_override_applies_only_to_primary(patch_providers):
    providers = patch_providers(
        {
            "gemini": _FakeProvider(provider_name="gemini", available=False, result="unused"),
            "anthropic": _FakeProvider(provider_name="anthropic", result="ok"),
        }
    )

    out = clean_transcript("hello", user_provider="gemini", model="gemini-2.5-pro")
    assert out == "ok"
    # Primary (gemini) was unavailable, so override never reached it.
    assert providers["gemini"].calls == []
    # Fallback (anthropic) MUST receive its own provider-specific default,
    # never the gemini model id.
    assert providers["anthropic"].calls[-1][1] == "claude-haiku-4-5-20251001"


def test_explicit_model_override_used_for_primary_when_available(patch_providers):
    providers = patch_providers({"gemini": _FakeProvider(provider_name="gemini", result="ok")})
    clean_transcript("hello", user_provider="gemini", model="gemini-2.5-pro")
    assert providers["gemini"].calls[-1][1] == "gemini-2.5-pro"


def test_auto_provider_ignores_model_override(patch_providers):
    providers = patch_providers({"gemini": _FakeProvider(provider_name="gemini", result="ok")})
    clean_transcript("hello", user_provider="auto", model="gemini-2.5-pro")
    # auto -> no explicit primary, override is ignored, provider default wins
    assert providers["gemini"].calls[-1][1] == "gemini-flash-lite-latest"


def test_build_prompt_is_stable_regardless_of_language_arg():
    """The prompt is intentionally language-agnostic — the 'same language as
    input' rule does the work, so the optional language arg is a no-op."""
    assert _build_prompt("hello", language="French") == _build_prompt("hello", language="auto")
    assert _build_prompt("hello", language=None) == _build_prompt("hello", language="fr")
