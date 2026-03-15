"""Unit tests for LLM provider implementations with mocked SDKs."""

from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# NullLLMProvider
# ---------------------------------------------------------------------------


def test_null_provider_name():
    from dicton.adapters.llm.provider import NullLLMProvider

    p = NullLLMProvider()
    assert p.name == "None"


def test_null_provider_not_available():
    from dicton.adapters.llm.provider import NullLLMProvider

    assert NullLLMProvider().is_available() is False


def test_null_provider_complete_returns_none():
    from dicton.adapters.llm.provider import NullLLMProvider

    assert NullLLMProvider().complete("hello") is None


# ---------------------------------------------------------------------------
# GeminiLLMProvider
# ---------------------------------------------------------------------------


def _make_google_genai_mock(response_text: str = "mocked response") -> ModuleType:
    """Build a fake google.genai module hierarchy."""
    mock_response = MagicMock()
    mock_response.text = response_text

    mock_models = MagicMock()
    mock_models.generate_content.return_value = mock_response

    mock_client = MagicMock()
    mock_client.models = mock_models

    mock_client_cls = MagicMock(return_value=mock_client)

    mock_types = MagicMock()
    mock_types.GenerateContentConfig.return_value = MagicMock()
    mock_types.HttpOptions.return_value = MagicMock()

    mock_genai = MagicMock()
    mock_genai.Client = mock_client_cls
    mock_genai.types = mock_types

    mock_google = MagicMock()
    mock_google.genai = mock_genai

    return mock_google, mock_genai, mock_client


@pytest.fixture()
def gemini_env(monkeypatch):
    """Patch GEMINI_API_KEY and fake google.genai."""
    mock_google, mock_genai, mock_client = _make_google_genai_mock()

    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")

    # Inject fake modules
    sys.modules.setdefault("google", mock_google)
    sys.modules["google.genai"] = mock_genai
    sys.modules["google.genai.types"] = mock_genai.types

    # Ensure config picks up the env var
    from dicton.shared.config import config

    monkeypatch.setattr(config, "GEMINI_API_KEY", "test-gemini-key")

    yield mock_genai, mock_client

    # Clean up module cache so other tests get a clean slate
    for mod in ["google", "google.genai", "google.genai.types"]:
        sys.modules.pop(mod, None)


def test_gemini_provider_name():
    from dicton.adapters.llm.gemini import GeminiLLMProvider

    assert GeminiLLMProvider().name == "gemini"


def test_gemini_is_available_without_key(monkeypatch):
    from dicton.shared.config import config

    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    from dicton.adapters.llm.gemini import GeminiLLMProvider

    assert GeminiLLMProvider().is_available() is False


def test_gemini_is_available_with_key_and_sdk(gemini_env):
    from dicton.adapters.llm.gemini import GeminiLLMProvider

    assert GeminiLLMProvider().is_available() is True


def test_gemini_complete_returns_text(gemini_env):
    from dicton.adapters.llm.gemini import GeminiLLMProvider

    provider = GeminiLLMProvider()
    result = provider.complete("Say hello")
    assert result == "mocked response"


def test_gemini_complete_returns_none_when_no_text(monkeypatch, gemini_env):
    mock_genai, mock_client = gemini_env
    mock_client.models.generate_content.return_value.text = None

    from dicton.adapters.llm.gemini import GeminiLLMProvider

    provider = GeminiLLMProvider()
    result = provider.complete("Say hello")
    assert result is None


def test_gemini_cleanup_clears_client(gemini_env):
    from dicton.adapters.llm.gemini import GeminiLLMProvider

    provider = GeminiLLMProvider()
    provider.complete("warm up")  # triggers client init
    assert provider._client is not None
    provider.cleanup()
    assert provider._client is None


# ---------------------------------------------------------------------------
# AnthropicLLMProvider
# ---------------------------------------------------------------------------


def _make_anthropic_mock(response_text: str = "anthropic response") -> MagicMock:
    mock_content_block = MagicMock()
    mock_content_block.text = response_text

    mock_message = MagicMock()
    mock_message.content = [mock_content_block]

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_message

    mock_anthropic_module = MagicMock()
    mock_anthropic_module.Anthropic.return_value = mock_client

    return mock_anthropic_module, mock_client


@pytest.fixture()
def anthropic_env(monkeypatch):
    """Patch ANTHROPIC_API_KEY and fake anthropic SDK."""
    mock_module, mock_client = _make_anthropic_mock()

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")
    sys.modules["anthropic"] = mock_module

    from dicton.shared.config import config

    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "test-anthropic-key")

    yield mock_module, mock_client

    sys.modules.pop("anthropic", None)


def test_anthropic_provider_name():
    from dicton.adapters.llm.anthropic import AnthropicLLMProvider

    assert AnthropicLLMProvider().name == "anthropic"


def test_anthropic_is_available_without_key(monkeypatch):
    from dicton.shared.config import config

    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "")
    from dicton.adapters.llm.anthropic import AnthropicLLMProvider

    assert AnthropicLLMProvider().is_available() is False


def test_anthropic_is_available_with_key_and_sdk(anthropic_env):
    from dicton.adapters.llm.anthropic import AnthropicLLMProvider

    assert AnthropicLLMProvider().is_available() is True


def test_anthropic_complete_returns_text(anthropic_env):
    from dicton.adapters.llm.anthropic import AnthropicLLMProvider

    provider = AnthropicLLMProvider()
    result = provider.complete("Say hello")
    assert result == "anthropic response"


def test_anthropic_complete_returns_none_when_no_content(monkeypatch, anthropic_env):
    mock_module, mock_client = anthropic_env
    mock_client.messages.create.return_value.content = []

    from dicton.adapters.llm.anthropic import AnthropicLLMProvider

    provider = AnthropicLLMProvider()
    result = provider.complete("Say hello")
    assert result is None


def test_anthropic_cleanup_closes_client(anthropic_env):
    from dicton.adapters.llm.anthropic import AnthropicLLMProvider

    provider = AnthropicLLMProvider()
    provider.complete("warm up")  # triggers client init
    assert provider._client is not None
    provider.cleanup()
    assert provider._client is None
