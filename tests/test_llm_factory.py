"""Unit tests for the LLM provider factory: fallback chain, caching, cleanup."""

from __future__ import annotations

import pytest

from dicton.adapters.llm.factory import (
    _PROVIDER_REGISTRY,
    DEFAULT_FALLBACK_ORDER,
    _provider_cache,
    cleanup,
    get_llm_provider,
    get_llm_provider_with_fallback,
)
from dicton.adapters.llm.provider import LLMProvider, NullLLMProvider

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


class _AlwaysAvailableProvider(LLMProvider):
    def __init__(self):
        self.cleanup_called = False

    @property
    def name(self) -> str:
        return "always"

    def is_available(self) -> bool:
        return True

    def complete(self, prompt: str) -> str | None:
        return "ok"

    def cleanup(self) -> None:
        self.cleanup_called = True


class _NeverAvailableProvider(LLMProvider):
    @property
    def name(self) -> str:
        return "never"

    def is_available(self) -> bool:
        return False

    def complete(self, prompt: str) -> str | None:
        return None


@pytest.fixture(autouse=True)
def _clean_factory_state():
    """Isolate factory module state between tests."""
    old_registry = dict(_PROVIDER_REGISTRY)
    old_cache = dict(_provider_cache)
    _PROVIDER_REGISTRY.clear()
    _provider_cache.clear()
    yield
    _PROVIDER_REGISTRY.clear()
    _provider_cache.clear()
    _PROVIDER_REGISTRY.update(old_registry)
    _provider_cache.update(old_cache)


# ---------------------------------------------------------------------------
# get_llm_provider
# ---------------------------------------------------------------------------


def test_get_unknown_provider_returns_null():
    provider = get_llm_provider("nonexistent", use_cache=False)
    assert isinstance(provider, NullLLMProvider)


def test_get_registered_available_provider():
    _PROVIDER_REGISTRY["always"] = _AlwaysAvailableProvider
    provider = get_llm_provider("always", use_cache=False)
    assert isinstance(provider, _AlwaysAvailableProvider)


def test_get_registered_unavailable_provider_returns_null():
    _PROVIDER_REGISTRY["never"] = _NeverAvailableProvider
    provider = get_llm_provider("never", use_cache=False)
    assert isinstance(provider, NullLLMProvider)


def test_caching_returns_same_instance():
    _PROVIDER_REGISTRY["always"] = _AlwaysAvailableProvider
    p1 = get_llm_provider("always", use_cache=True)
    p2 = get_llm_provider("always", use_cache=True)
    assert p1 is p2


def test_no_cache_returns_new_instance():
    _PROVIDER_REGISTRY["always"] = _AlwaysAvailableProvider
    p1 = get_llm_provider("always", use_cache=False)
    p2 = get_llm_provider("always", use_cache=False)
    assert p1 is not p2


# ---------------------------------------------------------------------------
# get_llm_provider_with_fallback
# ---------------------------------------------------------------------------


def test_fallback_returns_null_when_none_available(monkeypatch):
    from dicton.shared.config import config

    monkeypatch.setattr(config, "LLM_PROVIDER", "auto")
    provider = get_llm_provider_with_fallback(fallback_order=[], verbose=False)
    assert isinstance(provider, NullLLMProvider)


def test_fallback_uses_first_available():
    _PROVIDER_REGISTRY["never"] = _NeverAvailableProvider
    _PROVIDER_REGISTRY["always"] = _AlwaysAvailableProvider

    from dicton.shared.config import config

    # Simulate no user-configured provider
    original = config.LLM_PROVIDER
    config.LLM_PROVIDER = "auto"
    try:
        provider = get_llm_provider_with_fallback(fallback_order=["never", "always"], verbose=False)
        assert isinstance(provider, _AlwaysAvailableProvider)
    finally:
        config.LLM_PROVIDER = original


def test_fallback_respects_user_provider(monkeypatch):
    _PROVIDER_REGISTRY["always"] = _AlwaysAvailableProvider

    from dicton.shared.config import config

    monkeypatch.setattr(config, "LLM_PROVIDER", "always")
    provider = get_llm_provider_with_fallback(fallback_order=[], verbose=False)
    assert isinstance(provider, _AlwaysAvailableProvider)


# ---------------------------------------------------------------------------
# cleanup
# ---------------------------------------------------------------------------


def test_cleanup_calls_provider_cleanup():
    _PROVIDER_REGISTRY["always"] = _AlwaysAvailableProvider
    provider = get_llm_provider("always", use_cache=True)
    assert isinstance(provider, _AlwaysAvailableProvider)

    cleanup()

    assert provider.cleanup_called
    assert len(_provider_cache) == 0


def test_cleanup_clears_cache():
    _PROVIDER_REGISTRY["always"] = _AlwaysAvailableProvider
    get_llm_provider("always", use_cache=True)
    assert "always" in _provider_cache

    cleanup()

    assert len(_provider_cache) == 0


# ---------------------------------------------------------------------------
# DEFAULT_FALLBACK_ORDER
# ---------------------------------------------------------------------------


def test_default_fallback_order_contains_gemini_and_anthropic():
    assert "gemini" in DEFAULT_FALLBACK_ORDER
    assert "anthropic" in DEFAULT_FALLBACK_ORDER
