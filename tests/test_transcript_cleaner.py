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
        result: str | None = "cleaned text",
        available: bool = True,
        raise_on_call: Exception | None = None,
    ) -> None:
        self._result = result
        self._available = available
        self._raise = raise_on_call
        self.calls: list[tuple[str, str | None]] = []

    @property
    def name(self) -> str:
        return "fake"

    def is_available(self) -> bool:
        return self._available

    def complete(self, prompt: str, *, model: str | None = None) -> str | None:
        self.calls.append((prompt, model))
        if self._raise is not None:
            raise self._raise
        return self._result


@pytest.fixture
def patch_provider(monkeypatch):
    """Patch the cleaner to use a single fake provider in the fallback chain."""

    def _patch(provider: LLMProvider, order: tuple[str, ...] = ("fake",)):
        monkeypatch.setattr(
            "dicton.adapters.llm.cleaner.DEFAULT_FALLBACK_ORDER",
            list(order),
        )

        def _get(name: str, use_cache: bool = True):
            if name == "fake":
                return provider
            from dicton.adapters.llm.provider import NullLLMProvider

            return NullLLMProvider()

        monkeypatch.setattr("dicton.adapters.llm.cleaner.get_llm_provider", _get)
        # ``_register_providers`` is called inside clean_transcript; no-op it.
        monkeypatch.setattr("dicton.adapters.llm.cleaner._register_providers", lambda: None)
        return provider

    yield _patch
    # Reset cache so other tests don't see the fake.
    factory_module._provider_cache.clear()


def test_happy_path_returns_provider_text(patch_provider):
    fake = patch_provider(_FakeProvider(result="je voulais te dire bonjour."))
    out = clean_transcript("euh, je voulais, euh, te dire bonjour")
    assert out == "je voulais te dire bonjour."
    assert fake.calls, "provider should be called"


def test_fail_open_returns_none_on_exception(patch_provider):
    patch_provider(_FakeProvider(raise_on_call=RuntimeError("boom")))
    assert clean_transcript("hello world") is None


def test_provider_unavailable_returns_none(patch_provider):
    patch_provider(_FakeProvider(available=False))
    assert clean_transcript("hello world") is None


def test_none_string_sentinel_propagates(patch_provider):
    patch_provider(_FakeProvider(result="None"))
    out = clean_transcript("...")
    assert out == "None"


def test_empty_input_returns_none(patch_provider):
    fake = patch_provider(_FakeProvider(result="should not be called"))
    assert clean_transcript("") is None
    assert fake.calls == []


def test_prompt_embeds_bracket_removal_rule(patch_provider):
    fake = patch_provider(_FakeProvider(result="ok"))
    clean_transcript("hello [bruit] world", language="fr")
    prompt, _model = fake.calls[0]
    assert "[bruit]" in prompt or "bracketed" in prompt.lower()
    assert "filler" in prompt.lower()
    assert "fr" in prompt.lower()


def test_model_override_propagated_to_provider(patch_provider):
    fake = patch_provider(_FakeProvider(result="ok"))
    clean_transcript("hello", model="gemini-flash-lite-latest")
    _prompt, model = fake.calls[0]
    assert model == "gemini-flash-lite-latest"


def test_build_prompt_includes_language_when_specified():
    prompt = _build_prompt("hello", language="French")
    assert "French" in prompt


def test_build_prompt_omits_language_when_auto():
    prompt = _build_prompt("hello", language="auto")
    assert "auto" not in prompt.lower()
