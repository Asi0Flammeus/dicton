"""Gladia STT Provider for Dicton - WebSocket streaming + native translation.

Primary STT provider with superior features for real-time dictation:
- Real-time streaming via WebSocket (near-zero perceived latency)
- Native translation (no separate LLM call needed)
- 100+ languages with auto-detection
- Audio intelligence features (diarization, punctuation enhancement)

Documentation:
- Live API: https://docs.gladia.io/api-reference/v2/live
- Translation: https://docs.gladia.io/chapters/audio-intelligence/pages/translation
- Pricing: https://www.gladia.io/pricing ($0.61-0.75/hr, 10hr free/mo)
"""

import asyncio
import base64
import json
import threading
from typing import Callable, Generator

import requests

from .stt_provider import (
    STTCapability,
    STTProvider,
    STTProviderConfig,
    TranscriptionResult,
    WordInfo,
)


class GladiaSTTProvider(STTProvider):
    """Gladia Speech-to-Text provider with streaming and translation.

    Capabilities:
    - BATCH: Upload complete audio file for transcription
    - STREAMING: Real-time WebSocket streaming during recording
    - TRANSLATION: Built-in translation (no separate LLM call needed)
    - WORD_TIMESTAMPS: Per-word timing information

    Streaming Flow (for near-zero perceived latency):
        1. POST /v2/live → get unique WebSocket URL with token
        2. Connect to WebSocket BEFORE recording starts
        3. Send audio chunks as base64 DURING recording
        4. Receive partial transcripts in real-time
        5. Send stop_recording message → get final transcript

    Usage:
        config = STTProviderConfig(
            api_key="your_gladia_key",
            sample_rate=16000
        )
        provider = GladiaSTTProvider(config)

        # Batch mode
        result = provider.transcribe(audio_bytes)

        # Streaming mode (call at START of recording)
        result = provider.stream_transcribe(
            audio_generator,
            on_partial=lambda r: print(f"Partial: {r.text}")
        )

        # Native translation
        result = provider.translate(audio_bytes, target_language="en")
    """

    API_BASE = "https://api.gladia.io"

    @property
    def name(self) -> str:
        """Return provider name."""
        return "Gladia"

    @property
    def capabilities(self) -> set[STTCapability]:
        """Return supported capabilities."""
        return {
            STTCapability.BATCH,
            STTCapability.STREAMING,
            STTCapability.TRANSLATION,
            STTCapability.WORD_TIMESTAMPS,
        }

    def is_available(self) -> bool:
        """Check if Gladia is available.

        Returns:
            True if API key is set. SDK (websockets) is optional for batch mode.
        """
        return bool(self.config.api_key)

    def _get_headers(self) -> dict:
        """Get API headers with authentication.

        Returns:
            Headers dict with x-gladia-key and Content-Type
        """
        return {
            "x-gladia-key": self.config.api_key,
            "Content-Type": "application/json",
        }

    def _get_upload_headers(self) -> dict:
        """Get headers for file upload (no Content-Type, let requests set it).

        Returns:
            Headers dict with x-gladia-key only
        """
        return {
            "x-gladia-key": self.config.api_key,
        }

    def transcribe(self, audio_data: bytes, audio_format: str = "wav") -> TranscriptionResult | None:
        """Transcribe audio using Gladia batch API.

        Args:
            audio_data: Raw audio bytes (WAV format)
            audio_format: Audio format identifier

        Returns:
            TranscriptionResult with text and metadata, or None on failure
        """
        if not self.is_available():
            return None

        try:
            # Use pre-recorded transcription endpoint
            url = f"{self.API_BASE}/v2/pre-recorded"

            # Prepare multipart form data
            files = {
                "audio": (f"audio.{audio_format}", audio_data, f"audio/{audio_format}"),
            }

            response = requests.post(
                url,
                headers=self._get_upload_headers(),
                files=files,
                timeout=self.config.timeout,
            )
            response.raise_for_status()

            result = response.json()

            # Handle async processing - poll for result
            if "result_url" in result:
                return self._poll_for_result(result["result_url"])

            # Direct result (shouldn't happen with v2, but handle it)
            return self._parse_transcription_result(result)

        except Exception as e:
            from .config import config

            if config.DEBUG:
                print(f"Gladia batch STT error: {e}")
            raise

    def _poll_for_result(self, result_url: str, max_attempts: int = 60) -> TranscriptionResult | None:
        """Poll for async transcription result.

        Args:
            result_url: URL to poll for result
            max_attempts: Maximum polling attempts (1 second each)

        Returns:
            TranscriptionResult when ready, or None on timeout
        """
        import time

        for _ in range(max_attempts):
            response = requests.get(
                result_url,
                headers=self._get_headers(),
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()

            status = data.get("status")
            if status == "done":
                return self._parse_transcription_result(data.get("result", {}))
            elif status == "error":
                from .config import config

                if config.DEBUG:
                    print(f"Gladia transcription error: {data.get('error')}")
                return None

            time.sleep(1)

        return None

    def _parse_transcription_result(self, data: dict) -> TranscriptionResult | None:
        """Parse Gladia API response into TranscriptionResult.

        Args:
            data: Raw API response data

        Returns:
            TranscriptionResult or None if no text
        """
        # Extract full transcript
        transcription = data.get("transcription", {})
        text = transcription.get("full_transcript", "")

        if not text:
            # Try alternative response format
            text = data.get("prediction", "") or data.get("text", "")

        if not text:
            return None

        # Extract word-level info if available
        words = None
        utterances = transcription.get("utterances", [])
        if utterances:
            words = []
            for utterance in utterances:
                for word_data in utterance.get("words", []):
                    words.append(
                        WordInfo(
                            word=word_data.get("word", ""),
                            start=word_data.get("start", 0),
                            end=word_data.get("end", 0),
                            confidence=word_data.get("confidence"),
                        )
                    )

        # Extract translation if present
        translation = None
        translation_data = data.get("translation", {})
        if translation_data:
            # Handle list of translations
            if isinstance(translation_data, list) and translation_data:
                translation = translation_data[0].get("full_transcript", "")
            elif isinstance(translation_data, dict):
                translation = translation_data.get("full_transcript", "")

        return TranscriptionResult(
            text=text,
            language=transcription.get("language"),
            is_final=True,
            words=words,
            translation=translation,
            raw_response=data,
        )

    def translate(
        self,
        audio_data: bytes,
        target_language: str = "en",
        audio_format: str = "wav",
    ) -> TranscriptionResult | None:
        """Transcribe and translate audio in one operation.

        Uses Gladia's native translation feature - more efficient than
        separate transcription + LLM translation.

        Args:
            audio_data: Raw audio bytes (WAV format)
            target_language: Target language code (e.g., "en", "fr", "de")
            audio_format: Audio format identifier

        Returns:
            TranscriptionResult with both original text and translation
        """
        if not self.is_available():
            return None

        try:
            url = f"{self.API_BASE}/v2/pre-recorded"

            # Prepare request with translation config
            files = {
                "audio": (f"audio.{audio_format}", audio_data, f"audio/{audio_format}"),
            }

            # Translation configuration as form data
            data = {
                "translation_config": json.dumps({
                    "target_languages": [target_language],
                    "model": "base",
                }),
            }

            response = requests.post(
                url,
                headers=self._get_upload_headers(),
                files=files,
                data=data,
                timeout=self.config.timeout,
            )
            response.raise_for_status()

            result = response.json()

            # Handle async processing
            if "result_url" in result:
                return self._poll_for_result(result["result_url"])

            return self._parse_transcription_result(result)

        except Exception as e:
            from .config import config

            if config.DEBUG:
                print(f"Gladia translation error: {e}")
            raise

    def stream_transcribe(
        self,
        audio_generator: Generator[bytes, None, None],
        on_partial: Callable[[TranscriptionResult], None] | None = None,
    ) -> TranscriptionResult | None:
        """Stream audio for real-time transcription via WebSocket.

        This method should be called at the START of recording to enable
        streaming. Audio chunks are sent as they're captured, providing
        near-zero perceived latency when recording stops.

        Gladia V2 WebSocket flow:
        1. POST /v2/live to get unique WebSocket URL with auth token
        2. Connect to WebSocket
        3. Send audio chunks as base64-encoded messages
        4. Receive partial and final transcripts
        5. Send stop_recording to end session

        Args:
            audio_generator: Generator yielding raw PCM audio chunks
            on_partial: Optional callback for partial (interim) results

        Returns:
            Final TranscriptionResult when streaming ends, or None on failure
        """
        if not self.is_available():
            return None

        # Check if websockets is available
        try:
            import websockets  # noqa: F401
        except ImportError:
            from .config import config

            if config.DEBUG:
                print("Gladia streaming requires 'websockets' package. Using batch mode.")
            # Fall back to batch mode - collect all audio then transcribe
            audio_chunks = list(audio_generator)
            if not audio_chunks:
                return None
            full_audio = b"".join(audio_chunks)
            return self.transcribe(full_audio)

        # Run async streaming in sync context
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(
                self._async_stream_transcribe(audio_generator, on_partial)
            )
        finally:
            loop.close()

    async def _async_stream_transcribe(
        self,
        audio_generator: Generator[bytes, None, None],
        on_partial: Callable[[TranscriptionResult], None] | None = None,
    ) -> TranscriptionResult | None:
        """Async implementation of streaming transcription.

        Args:
            audio_generator: Generator yielding raw PCM audio chunks
            on_partial: Optional callback for partial results

        Returns:
            Final TranscriptionResult or None on failure
        """
        import websockets

        # Step 1: Initialize live session and get WebSocket URL
        init_payload = {
            "encoding": "wav/pcm",
            "sample_rate": self.config.sample_rate,
            "bit_depth": 16,
            "channels": 1,
            "language_config": {
                "languages": [],  # Empty for auto-detect
                "code_switching": True,  # Allow language changes mid-stream
            },
            "realtime_processing": {
                "words_accurate_timestamps": True,
            },
            "messages_config": {
                "receive_partial_transcripts": on_partial is not None,
                "receive_final_transcripts": True,
            },
        }

        # Add language hint if configured
        if self.config.language:
            init_payload["language_config"]["languages"] = [self.config.language]
            init_payload["language_config"]["code_switching"] = False

        try:
            init_response = requests.post(
                f"{self.API_BASE}/v2/live",
                headers=self._get_headers(),
                json=init_payload,
                timeout=10,
            )
            init_response.raise_for_status()
            ws_url = init_response.json()["url"]
        except Exception as e:
            from .config import config

            if config.DEBUG:
                print(f"Gladia live init error: {e}")
            return None

        # Step 2: Connect and stream
        final_text_parts = []
        final_result = None

        try:
            async with websockets.connect(ws_url) as ws:
                # Create tasks for sending and receiving
                send_complete = asyncio.Event()

                async def send_audio():
                    """Send audio chunks to WebSocket."""
                    try:
                        for chunk in audio_generator:
                            # Send audio as base64-encoded JSON message
                            message = {
                                "type": "audio_chunk",
                                "data": {
                                    "chunk": base64.b64encode(chunk).decode("utf-8"),
                                },
                            }
                            await ws.send(json.dumps(message))
                    finally:
                        # Signal end of audio
                        await ws.send(json.dumps({"type": "stop_recording"}))
                        send_complete.set()

                async def receive_transcripts():
                    """Receive transcription results from WebSocket."""
                    nonlocal final_text_parts, final_result

                    try:
                        async for message in ws:
                            data = json.loads(message)
                            msg_type = data.get("type")

                            if msg_type == "transcript":
                                transcript_data = data.get("data", {})
                                utterance = transcript_data.get("utterance", {})
                                text = utterance.get("text", "")
                                is_final = transcript_data.get("is_final", False)

                                result = TranscriptionResult(
                                    text=text,
                                    language=utterance.get("language"),
                                    confidence=utterance.get("confidence"),
                                    is_final=is_final,
                                )

                                if is_final and text:
                                    final_text_parts.append(text)
                                elif on_partial and text:
                                    on_partial(result)

                            elif msg_type == "post_final_transcript":
                                # Complete transcript at end of session
                                full_text = data.get("data", {}).get("full_transcript", "")
                                if full_text:
                                    final_result = TranscriptionResult(
                                        text=full_text,
                                        is_final=True,
                                        raw_response=data,
                                    )

                            elif msg_type == "error":
                                from .config import config

                                if config.DEBUG:
                                    print(f"Gladia stream error: {data}")
                                break

                    except websockets.exceptions.ConnectionClosed:
                        pass  # Normal closure

                # Run both tasks concurrently
                await asyncio.gather(
                    send_audio(),
                    receive_transcripts(),
                    return_exceptions=True,
                )

        except Exception as e:
            from .config import config

            if config.DEBUG:
                print(f"Gladia streaming error: {e}")
            return None

        # Return final result
        if final_result:
            return final_result
        elif final_text_parts:
            return TranscriptionResult(
                text=" ".join(final_text_parts).strip(),
                is_final=True,
            )

        return None

    def stream_translate(
        self,
        audio_generator: Generator[bytes, None, None],
        target_language: str = "en",
        on_partial: Callable[[TranscriptionResult], None] | None = None,
    ) -> TranscriptionResult | None:
        """Stream audio with real-time translation.

        Combines streaming transcription with native translation.

        Args:
            audio_generator: Generator yielding raw PCM audio chunks
            target_language: Target language code
            on_partial: Optional callback for partial results

        Returns:
            Final TranscriptionResult with translation, or None on failure
        """
        # Note: Gladia streaming translation requires configuring translation
        # in the initial /v2/live request. This is a placeholder for future
        # implementation when we integrate streaming into the recording flow.

        # For now, fall back to batch translation
        audio_chunks = list(audio_generator)
        if not audio_chunks:
            return None
        full_audio = b"".join(audio_chunks)
        return self.translate(full_audio, target_language)
