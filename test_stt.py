#!/usr/bin/env python3
"""Quick STT provider test script.

Usage:
    # Test with default provider (from .env)
    python test_stt.py

    # Force specific provider
    python test_stt.py gladia
    python test_stt.py elevenlabs

    # Verbose mode
    DEBUG=true python test_stt.py gladia
"""

import os
import sys

# Add src to path for development
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from dicton.config import config
from dicton.stt_factory import (
    get_stt_provider,
    get_stt_provider_with_fallback,
    get_available_stt_providers,
)


def main():
    print("=" * 60)
    print("STT Provider Test")
    print("=" * 60)

    # Show config
    print(f"\nConfiguration:")
    print(f"  STT_PROVIDER: {config.STT_PROVIDER}")
    print(f"  STT_MODE: {config.STT_MODE}")
    print(f"  GLADIA_API_KEY: {'set (' + config.GLADIA_API_KEY[:8] + '...)' if config.GLADIA_API_KEY else 'NOT SET'}")
    print(f"  ELEVENLABS_API_KEY: {'set (' + config.ELEVENLABS_API_KEY[:8] + '...)' if config.ELEVENLABS_API_KEY else 'NOT SET'}")

    # List available providers
    available = get_available_stt_providers()
    print(f"\nAvailable providers: {available}")

    # Get provider (from CLI arg or default)
    provider_name = sys.argv[1] if len(sys.argv) > 1 else None

    if provider_name:
        print(f"\nTesting specific provider: {provider_name}")
        provider = get_stt_provider(provider_name)
    else:
        print(f"\nTesting with fallback (primary: {config.STT_PROVIDER})")
        provider = get_stt_provider_with_fallback()

    # Show provider info
    print(f"\nProvider details:")
    print(f"  Name: {provider.name}")
    print(f"  Available: {provider.is_available()}")
    print(f"  Capabilities: {[c.name for c in provider.capabilities]}")
    print(f"  Supports streaming: {provider.supports_streaming()}")
    print(f"  Supports translation: {provider.supports_translation()}")

    if not provider.is_available():
        print("\n❌ Provider not available!")
        if provider_name == "gladia" or (not provider_name and config.STT_PROVIDER == "gladia"):
            print("   → Check that GLADIA_API_KEY is set in ~/.config/dicton/.env")
        return 1

    # Quick API test (no actual audio)
    print("\n" + "-" * 60)
    print("Testing API connectivity...")

    if provider.name == "Gladia":
        # Test Gladia API endpoint
        import requests
        try:
            headers = {"x-gladia-key": config.GLADIA_API_KEY}
            # Just check if we can reach the API (will fail without audio, but proves connectivity)
            resp = requests.post(
                "https://api.gladia.io/v2/upload",
                headers=headers,
                timeout=10
            )
            if resp.status_code == 400:
                # 400 = "no file" which means API key worked!
                print("✓ Gladia API key is valid (got expected 'no file' error)")
            elif resp.status_code == 401:
                print("❌ Gladia API key is INVALID (401 Unauthorized)")
                return 1
            else:
                print(f"? Gladia API returned: {resp.status_code} - {resp.text[:100]}")
        except Exception as e:
            print(f"❌ Gladia API error: {e}")
            return 1

    elif provider.name == "ElevenLabs":
        try:
            from elevenlabs.client import ElevenLabs
            client = ElevenLabs(api_key=config.ELEVENLABS_API_KEY)
            # This will fail without audio but proves SDK works
            print("✓ ElevenLabs SDK initialized")
        except Exception as e:
            print(f"❌ ElevenLabs error: {e}")
            return 1

    print("\n" + "=" * 60)
    print(f"✓ {provider.name} is ready for use!")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
