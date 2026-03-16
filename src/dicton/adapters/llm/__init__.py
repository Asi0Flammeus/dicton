"""LLM provider package for Dicton.

Public API mirrors the old llm_processor module for backward compatibility.
"""

from __future__ import annotations

from .factory import cleanup, get_available_providers, get_llm_provider_with_fallback
from .prompts import act_on_text, reformulate, translate


def is_available() -> bool:
    """Check if at least one LLM provider is configured and available."""
    provider = get_llm_provider_with_fallback(verbose=False)
    return provider.is_available()


__all__ = [
    "act_on_text",
    "reformulate",
    "translate",
    "is_available",
    "cleanup",
    "get_available_providers",
    "get_llm_provider_with_fallback",
]
