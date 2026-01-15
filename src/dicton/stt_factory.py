"""STT Provider Factory for Dicton.

Provides factory functions and fallback mechanism for STT providers,
following the pattern established in llm_processor.py.

Usage:
    # Get primary provider with automatic fallback
    provider = get_stt_provider_with_fallback()
    if provider.is_available():
        result = provider.transcribe(audio_bytes)

    # Get specific provider
    gladia = get_stt_provider("gladia")
    elevenlabs = get_stt_provider("elevenlabs")

    # List available providers
    available = get_available_stt_providers()  # ["gladia", "elevenlabs"]
"""

from .config import config
from .stt_provider import NullSTTProvider, STTProvider, STTProviderConfig

# Cached provider instances (singleton pattern)
_providers: dict[str, STTProvider] = {}


def _create_elevenlabs_provider() -> STTProvider | None:
    """Create ElevenLabs provider if configured.

    Returns:
        ElevenLabsSTTProvider instance or None if not available
    """
    if not config.ELEVENLABS_API_KEY:
        return None

    try:
        from .stt_elevenlabs import ElevenLabsSTTProvider

        provider_config = STTProviderConfig(
            api_key=config.ELEVENLABS_API_KEY,
            model=config.ELEVENLABS_MODEL,
            timeout=config.STT_TIMEOUT,
            language=None,  # Auto-detect
            sample_rate=config.SAMPLE_RATE,
        )
        return ElevenLabsSTTProvider(provider_config)
    except ImportError:
        return None


def _create_gladia_provider() -> STTProvider | None:
    """Create Gladia provider if configured.

    Returns:
        GladiaSTTProvider instance or None if not available
    """
    gladia_key = getattr(config, "GLADIA_API_KEY", "")
    if not gladia_key:
        return None

    try:
        from .stt_gladia import GladiaSTTProvider

        provider_config = STTProviderConfig(
            api_key=gladia_key,
            model=getattr(config, "GLADIA_MODEL", ""),
            timeout=config.STT_TIMEOUT,
            language=None,  # Auto-detect
            sample_rate=config.SAMPLE_RATE,
        )
        return GladiaSTTProvider(provider_config)
    except ImportError:
        return None


def get_stt_provider(name: str | None = None) -> STTProvider:
    """Get STT provider by name or use configured default.

    Args:
        name: Provider name ("elevenlabs", "gladia") or None for default
              Default is determined by STT_PROVIDER config

    Returns:
        STTProvider instance (may be NullSTTProvider if unavailable)
    """
    global _providers

    # Determine which provider to use
    if name is None:
        name = getattr(config, "STT_PROVIDER", "elevenlabs").lower()

    # Return cached instance if available
    if name in _providers:
        return _providers[name]

    # Create provider based on name
    provider: STTProvider | None = None

    if name == "elevenlabs":
        provider = _create_elevenlabs_provider()
    elif name == "gladia":
        provider = _create_gladia_provider()

    # Fall back to NullSTTProvider if creation failed or provider unavailable
    if provider is None or not provider.is_available():
        provider = NullSTTProvider()

    _providers[name] = provider
    return provider


def get_stt_provider_with_fallback() -> STTProvider:
    """Get primary STT provider with fallback to alternative.

    Similar to LLM processor's fallback mechanism:
    1. Try primary provider (STT_PROVIDER config)
    2. Fall back to alternative if primary unavailable or fails

    The fallback order depends on STT_PROVIDER:
    - If "gladia": Try Gladia first, then ElevenLabs
    - If "elevenlabs": Try ElevenLabs first, then Gladia

    Returns:
        First available STTProvider, or NullSTTProvider if none available
    """
    primary = getattr(config, "STT_PROVIDER", "elevenlabs").lower()

    # Define fallback order based on primary preference
    if primary == "gladia":
        order = ["gladia", "elevenlabs"]
    else:
        order = ["elevenlabs", "gladia"]

    for provider_name in order:
        provider = get_stt_provider(provider_name)
        if provider.is_available():
            return provider

    return NullSTTProvider()


def get_available_stt_providers() -> list[str]:
    """Get list of available STT provider names.

    Checks which providers have valid configuration and SDK installed.

    Returns:
        List of provider names that are available for use
    """
    providers = []

    # Check ElevenLabs
    if config.ELEVENLABS_API_KEY:
        try:
            from elevenlabs.client import ElevenLabs  # noqa: F401

            providers.append("elevenlabs")
        except ImportError:
            pass

    # Check Gladia
    gladia_key = getattr(config, "GLADIA_API_KEY", "")
    if gladia_key:
        try:
            import websockets  # noqa: F401

            providers.append("gladia")
        except ImportError:
            # Gladia batch mode works without websockets
            try:
                import requests  # noqa: F401

                providers.append("gladia")
            except ImportError:
                pass

    return providers


def clear_stt_provider_cache():
    """Clear cached provider instances.

    Useful for testing or when configuration changes.
    """
    global _providers
    _providers = {}
