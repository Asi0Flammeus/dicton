"""LLM provider ABC and null implementation."""

from __future__ import annotations

from abc import ABC, abstractmethod


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name of the provider."""

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if the provider has required credentials and dependencies."""

    @abstractmethod
    def complete(self, prompt: str, *, model: str | None = None) -> str | None:
        """Send prompt to the LLM and return the response text, or None on failure.

        ``model`` overrides the provider's default model for this call only.
        """

    def cleanup(self) -> None:  # noqa: B027
        """Release resources. Default is a no-op."""


class NullLLMProvider(LLMProvider):
    """Null implementation used when no provider is configured."""

    @property
    def name(self) -> str:
        return "None"

    def is_available(self) -> bool:
        return False

    def complete(self, prompt: str, *, model: str | None = None) -> str | None:
        return None
