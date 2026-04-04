"""LLM provider factory with fallback chain and caching."""

from __future__ import annotations

import logging

from .provider import LLMProvider, NullLLMProvider

logger = logging.getLogger(__name__)

_PROVIDER_REGISTRY: dict[str, type[LLMProvider]] = {}
_provider_cache: dict[str, LLMProvider] = {}

DEFAULT_FALLBACK_ORDER = ["gemini", "anthropic"]


def _register_providers() -> None:
    global _PROVIDER_REGISTRY

    if _PROVIDER_REGISTRY:
        return

    try:
        from .gemini import GeminiLLMProvider

        _PROVIDER_REGISTRY["gemini"] = GeminiLLMProvider
    except ImportError:
        logger.debug("Gemini provider not available")

    try:
        from .anthropic import AnthropicLLMProvider

        _PROVIDER_REGISTRY["anthropic"] = AnthropicLLMProvider
    except ImportError:
        logger.debug("Anthropic provider not available")


def get_llm_provider(name: str, use_cache: bool = True) -> LLMProvider:
    """Get an LLM provider by name."""
    _register_providers()
    name = name.lower()

    if use_cache and name in _provider_cache:
        return _provider_cache[name]

    if name not in _PROVIDER_REGISTRY:
        logger.warning(f"Unknown LLM provider: {name}")
        return NullLLMProvider()

    try:
        provider = _PROVIDER_REGISTRY[name]()
        if not provider.is_available():
            return NullLLMProvider()
        if use_cache:
            _provider_cache[name] = provider
        return provider
    except Exception as e:
        logger.error(f"Failed to initialize LLM provider '{name}': {e}")
        return NullLLMProvider()


def get_llm_provider_with_fallback(
    user_provider: str = "auto",
    fallback_order: list[str] | None = None,
    verbose: bool = True,
) -> LLMProvider:
    """Get the best available LLM provider with fallback chain.

    Args:
        user_provider: Preferred provider name (e.g. "gemini", "anthropic", "auto").
        fallback_order: Custom fallback order. Defaults to DEFAULT_FALLBACK_ORDER.
        verbose: Print warnings when preferred provider is unavailable.
    """
    _register_providers()

    user_provider = user_provider.lower()
    if user_provider and user_provider != "auto":
        provider = get_llm_provider(user_provider)
        if provider.is_available():
            return provider
        if verbose:
            print(f"⚠ LLM provider '{user_provider}' not available (check API key)")

    order = fallback_order or DEFAULT_FALLBACK_ORDER
    for name in order:
        provider = get_llm_provider(name)
        if provider.is_available():
            return provider

    return NullLLMProvider()


def get_available_providers() -> list[str]:
    """Return list of available and configured LLM provider names."""
    _register_providers()
    available = []
    for name in _PROVIDER_REGISTRY:
        try:
            provider = get_llm_provider(name, use_cache=False)
            if provider.is_available():
                available.append(name)
        except Exception:
            pass
    return available


def is_available() -> bool:
    """Check if at least one LLM provider is configured and available."""
    provider = get_llm_provider_with_fallback(user_provider="auto", verbose=False)
    return provider.is_available()


def cleanup() -> None:
    """Close all cached providers and clear the cache."""
    for provider in _provider_cache.values():
        try:
            provider.cleanup()
        except Exception:
            pass
    _provider_cache.clear()
