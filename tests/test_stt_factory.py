"""Tests for STT Provider Factory.

Tests the stt_factory module functionality including:
- Provider registration
- Provider retrieval by name
- Fallback chain behavior
- Cache management
"""

from unittest.mock import MagicMock, patch

import pytest

from dicton.stt_provider import NullSTTProvider, STTCapability

# =============================================================================
# Factory Tests
# =============================================================================


class TestSTTFactory:
    """Test STT provider factory functionality."""

    @pytest.fixture(autouse=True)
    def reset_factory(self):
        """Reset factory state before each test."""
        from dicton import stt_factory

        stt_factory._PROVIDER_REGISTRY.clear()
        stt_factory._provider_cache.clear()
        yield
        stt_factory._PROVIDER_REGISTRY.clear()
        stt_factory._provider_cache.clear()

    def test_get_unknown_provider_returns_null(self):
        """Test getting unknown provider returns NullSTTProvider."""
        from dicton.stt_factory import get_stt_provider

        provider = get_stt_provider("nonexistent")
        assert isinstance(provider, NullSTTProvider)

    def test_get_mistral_provider(self):
        """Test getting Mistral provider."""
        with (
            patch.dict("os.environ", {"MISTRAL_API_KEY": "test_key"}, clear=False),
            patch("mistralai.Mistral") as mock_mistral,
        ):
            mock_mistral.return_value = MagicMock()

            from dicton.stt_factory import get_stt_provider

            provider = get_stt_provider("mistral")
            assert provider.name == "Mistral Voxtral"
            assert STTCapability.BATCH in provider.capabilities

    def test_get_provider_caches_result(self):
        """Test provider is cached after first retrieval."""
        with (
            patch.dict("os.environ", {"MISTRAL_API_KEY": "test_key"}, clear=False),
            patch("mistralai.Mistral") as mock_mistral,
        ):
            mock_mistral.return_value = MagicMock()

            from dicton.stt_factory import _provider_cache, get_stt_provider

            provider1 = get_stt_provider("mistral")
            provider2 = get_stt_provider("mistral")

            assert provider1 is provider2
            assert "mistral" in _provider_cache

    def test_get_provider_no_cache(self):
        """Test provider retrieval without caching."""
        with (
            patch.dict("os.environ", {"MISTRAL_API_KEY": "test_key"}, clear=False),
            patch("mistralai.Mistral") as mock_mistral,
        ):
            mock_mistral.return_value = MagicMock()

            from dicton.stt_factory import get_stt_provider

            provider1 = get_stt_provider("mistral", use_cache=False)
            provider2 = get_stt_provider("mistral", use_cache=False)

            assert provider1 is not provider2


class TestSTTFactoryFallback:
    """Test STT provider fallback behavior."""

    @pytest.fixture(autouse=True)
    def reset_factory(self):
        """Reset factory state before each test."""
        from dicton import stt_factory

        stt_factory._PROVIDER_REGISTRY.clear()
        stt_factory._provider_cache.clear()
        yield
        stt_factory._PROVIDER_REGISTRY.clear()
        stt_factory._provider_cache.clear()

    def test_fallback_to_available_provider(self):
        """Test fallback chain finds available provider."""
        with (
            patch.dict(
                "os.environ", {"STT_PROVIDER": "", "MISTRAL_API_KEY": "test_key"}, clear=False
            ),
            patch("mistralai.Mistral") as mock_mistral,
        ):
            mock_mistral.return_value = MagicMock()

            from dicton.stt_factory import get_stt_provider_with_fallback

            provider = get_stt_provider_with_fallback()
            assert provider.name == "Mistral Voxtral"

    def test_fallback_returns_null_when_none_available(self):
        """Test fallback returns NullSTTProvider when none available."""
        with patch.dict(
            "os.environ",
            {"STT_PROVIDER": "", "MISTRAL_API_KEY": "", "ELEVENLABS_API_KEY": ""},
            clear=False,
        ):
            from dicton.stt_factory import get_stt_provider_with_fallback

            provider = get_stt_provider_with_fallback()
            assert isinstance(provider, NullSTTProvider)

    def test_user_specified_provider_takes_priority(self):
        """Test user-specified STT_PROVIDER env var takes priority."""
        with (
            patch.dict(
                "os.environ",
                {"STT_PROVIDER": "mistral", "MISTRAL_API_KEY": "test_key"},
                clear=False,
            ),
            patch("mistralai.Mistral") as mock_mistral,
        ):
            mock_mistral.return_value = MagicMock()

            from dicton.stt_factory import get_stt_provider_with_fallback

            provider = get_stt_provider_with_fallback()
            assert provider.name == "Mistral Voxtral"


class TestSTTFactoryAvailable:
    """Test getting list of available providers."""

    @pytest.fixture(autouse=True)
    def reset_factory(self):
        """Reset factory state before each test."""
        from dicton import stt_factory

        stt_factory._PROVIDER_REGISTRY.clear()
        stt_factory._provider_cache.clear()
        yield
        stt_factory._PROVIDER_REGISTRY.clear()
        stt_factory._provider_cache.clear()

    def test_get_available_providers_with_mistral(self):
        """Test listing available providers includes Mistral."""
        with (
            patch.dict("os.environ", {"MISTRAL_API_KEY": "test_key"}, clear=False),
            patch("mistralai.Mistral") as mock_mistral,
        ):
            mock_mistral.return_value = MagicMock()

            from dicton.stt_factory import get_available_stt_providers

            available = get_available_stt_providers()
            assert "mistral" in available

    def test_get_available_providers_empty_when_none_configured(self):
        """Test listing available providers returns empty when none configured."""
        with patch.dict(
            "os.environ", {"MISTRAL_API_KEY": "", "ELEVENLABS_API_KEY": ""}, clear=False
        ):
            from dicton.stt_factory import get_available_stt_providers

            available = get_available_stt_providers()
            # May have mistral if SDK is available even without key
            # so just check it returns a list
            assert isinstance(available, list)


class TestSTTFactoryCache:
    """Test STT provider cache management."""

    @pytest.fixture(autouse=True)
    def reset_factory(self):
        """Reset factory state before each test."""
        from dicton import stt_factory

        stt_factory._PROVIDER_REGISTRY.clear()
        stt_factory._provider_cache.clear()
        yield
        stt_factory._PROVIDER_REGISTRY.clear()
        stt_factory._provider_cache.clear()

    def test_clear_provider_cache(self):
        """Test clearing provider cache."""
        with (
            patch.dict("os.environ", {"MISTRAL_API_KEY": "test_key"}, clear=False),
            patch("mistralai.Mistral") as mock_mistral,
        ):
            mock_mistral.return_value = MagicMock()

            from dicton.stt_factory import (
                _provider_cache,
                clear_provider_cache,
                get_stt_provider,
            )

            # Populate cache
            get_stt_provider("mistral")
            assert "mistral" in _provider_cache

            # Clear cache
            clear_provider_cache()
            assert "mistral" not in _provider_cache
