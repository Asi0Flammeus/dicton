"""STT Provider Factory for Dicton

Manages STT provider instantiation with fallback chain support.
Providers are lazily initialized and cached for reuse.

Provider priority (configurable via STT_PROVIDER env var):
1. User-specified provider (if available)
2. Mistral (cost-effective default)
3. ElevenLabs (fallback)
4. NullSTTProvider (graceful degradation)
"""

import logging
import os
from typing import TYPE_CHECKING

from .stt_provider import NullSTTProvider, STTProvider, STTProviderConfig

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Provider registry - maps names to lazy loader functions
_PROVIDER_REGISTRY: dict[str, type[STTProvider]] = {}
_provider_cache: dict[str, STTProvider] = {}

# Default fallback order when no provider specified
DEFAULT_FALLBACK_ORDER = ["mistral", "elevenlabs"]


def _register_providers():
    """Register available providers.

    Called lazily on first access to avoid import cycles.
    """
    global _PROVIDER_REGISTRY

    if _PROVIDER_REGISTRY:
        return  # Already registered

    # Register Mistral provider
    try:
        from .stt_mistral import MistralSTTProvider

        _PROVIDER_REGISTRY["mistral"] = MistralSTTProvider
    except ImportError:
        logger.debug("Mistral provider not available (missing mistralai)")

    # Register ElevenLabs provider (if exists)
    try:
        from .stt_elevenlabs import ElevenLabsSTTProvider

        _PROVIDER_REGISTRY["elevenlabs"] = ElevenLabsSTTProvider
    except ImportError:
        logger.debug("ElevenLabs provider not available")


def get_stt_provider(
    name: str,
    config: STTProviderConfig | None = None,
    use_cache: bool = True,
) -> STTProvider:
    """Get an STT provider by name.

    Args:
        name: Provider name (e.g., "mistral", "elevenlabs").
        config: Optional configuration for the provider.
        use_cache: Whether to use cached provider instance.

    Returns:
        STTProvider instance. Returns NullSTTProvider if provider
        is not available or not configured.
    """
    _register_providers()

    name = name.lower()

    # Check cache first
    if use_cache and name in _provider_cache:
        return _provider_cache[name]

    # Check if provider is registered
    if name not in _PROVIDER_REGISTRY:
        logger.warning(f"Unknown STT provider: {name}")
        return NullSTTProvider()

    # Instantiate provider
    try:
        provider_class = _PROVIDER_REGISTRY[name]
        provider = provider_class(config)

        if not provider.is_available():
            logger.warning(f"STT provider '{name}' not available (missing API key?)")
            return NullSTTProvider()

        # Cache successful provider
        if use_cache:
            _provider_cache[name] = provider

        logger.info(f"Initialized STT provider: {provider.name}")
        return provider

    except Exception as e:
        logger.error(f"Failed to initialize STT provider '{name}': {e}")
        return NullSTTProvider()


def get_stt_provider_with_fallback(
    config: STTProviderConfig | None = None,
    fallback_order: list[str] | None = None,
    verbose: bool = True,
) -> STTProvider:
    """Get the best available STT provider with fallback.

    Tries providers in order until one is available.

    Args:
        config: Optional configuration for providers.
        fallback_order: List of provider names to try in order.
                       Defaults to DEFAULT_FALLBACK_ORDER.
        verbose: Print user-facing status messages.

    Returns:
        First available STTProvider, or NullSTTProvider if none available.
    """
    _register_providers()

    # Check for user-specified provider first
    user_provider = os.getenv("STT_PROVIDER", "").lower()
    if user_provider:
        provider = get_stt_provider(user_provider, config)
        if provider.is_available():
            if verbose:
                print(f"✓ STT Provider: {provider.name} (configured)")
            logger.info(f"Using user-specified STT provider: {provider.name}")
            return provider
        if verbose:
            print(f"⚠ STT Provider '{user_provider}' not available (check API key)")
        logger.warning(
            f"User-specified STT provider '{user_provider}' not available, trying fallbacks"
        )

    # Try fallback order
    order = fallback_order or DEFAULT_FALLBACK_ORDER
    is_fallback = bool(user_provider)  # If user specified one and it failed, next is fallback

    for name in order:
        provider = get_stt_provider(name, config, use_cache=True)
        if provider.is_available():
            if verbose:
                suffix = "(fallback)" if is_fallback else "(primary)"
                print(f"✓ STT Provider: {provider.name} {suffix}")
            logger.info(f"Initialized STT provider: {provider.name}")
            return provider
        logger.debug(f"STT provider '{name}' not available, trying next")
        is_fallback = True  # Next provider in chain is a fallback

    if verbose:
        print("⚠ No STT provider available")
    logger.warning("No STT providers available, using NullSTTProvider")
    return NullSTTProvider()


def get_available_stt_providers() -> list[str]:
    """Get list of available and configured STT providers.

    Returns:
        List of provider names that are available.
    """
    _register_providers()

    available = []
    for name in _PROVIDER_REGISTRY:
        try:
            provider = get_stt_provider(name, use_cache=False)
            if provider.is_available():
                available.append(name)
        except Exception:
            pass

    return available


def clear_provider_cache():
    """Clear the provider cache.

    Useful for testing or when configuration changes.
    """
    _provider_cache.clear()
