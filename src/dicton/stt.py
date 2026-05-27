"""Groq Whisper STT via direct httpx call.

Shares the AsyncClient with `cleanup` so STT + cleanup go through the same
TCP+TLS+HTTP/2 connection to api.groq.com.

We request ``verbose_json`` so each segment carries the decoder confidence
signals (``no_speech_prob``, ``avg_logprob``, ``compression_ratio``). These
let us drop hallucinated segments — the canned subtitle/sign-off phrases
Whisper emits on silence or low-SNR audio — by their statistical signature
rather than by string-matching known phrases.
"""

from __future__ import annotations

import contextlib
import io
import wave
from dataclasses import dataclass

import httpx
import numpy as np

GROQ_BASE = "https://api.groq.com/openai/v1"

# Hallucination thresholds. Anchored on OpenAI Whisper's own decode defaults
# (no_speech_threshold=0.6, logprob_threshold=-1.0, compression_ratio=2.4),
# tightened for our dictation use where dropping garbage matters more than
# keeping a doubtful word. Real speech sits well clear of all of these
# (observed: no_speech≈0.0, avg_logprob≈-0.7, compression_ratio≈0.7).
NO_SPEECH_PROB_CERTAIN = 0.8  # almost certainly silence → drop regardless
NO_SPEECH_PROB_LIKELY = 0.6  # likely silence; drop if confidence also weak
AVG_LOGPROB_WEAK = -0.7  # paired with NO_SPEECH_PROB_LIKELY
AVG_LOGPROB_GARBAGE = -1.0  # very low confidence → drop outright
COMPRESSION_RATIO_MAX = 2.4  # repetition loop ("merci merci merci…")


@dataclass(frozen=True)
class Segment:
    text: str
    no_speech_prob: float
    avg_logprob: float
    compression_ratio: float


@dataclass(frozen=True)
class Transcript:
    """A chunk's transcription as decoder segments plus their confidence."""

    segments: tuple[Segment, ...]

    @property
    def raw_text(self) -> str:
        return " ".join(s.text.strip() for s in self.segments if s.text.strip()).strip()

    def clean_text(self) -> str:
        """Join the segments that survive the hallucination filter."""
        kept = [s.text.strip() for s in self.segments if not is_hallucination(s)]
        return " ".join(t for t in kept if t).strip()

    @property
    def dropped(self) -> int:
        return sum(1 for s in self.segments if is_hallucination(s))


def is_hallucination(seg: Segment) -> bool:
    """True when a segment looks like a Whisper hallucination, not speech."""
    return (
        seg.no_speech_prob > NO_SPEECH_PROB_CERTAIN
        or (seg.no_speech_prob > NO_SPEECH_PROB_LIKELY and seg.avg_logprob < AVG_LOGPROB_WEAK)
        or seg.compression_ratio > COMPRESSION_RATIO_MAX
        or seg.avg_logprob < AVG_LOGPROB_GARBAGE
    )


def _parse_transcript(data: dict) -> Transcript:
    segments = data.get("segments") or []
    if not segments:
        # Very short audio sometimes returns no segments — keep the top-level
        # text with neutral metrics so it is never dropped by the filter.
        text = (data.get("text") or "").strip()
        if not text:
            return Transcript(segments=())
        return Transcript(
            segments=(
                Segment(text=text, no_speech_prob=0.0, avg_logprob=0.0, compression_ratio=1.0),
            )
        )
    return Transcript(
        segments=tuple(
            Segment(
                text=s.get("text", ""),
                no_speech_prob=float(s.get("no_speech_prob", 0.0)),
                avg_logprob=float(s.get("avg_logprob", 0.0)),
                compression_ratio=float(s.get("compression_ratio", 1.0)),
            )
            for s in segments
        )
    )


def pcm16_to_wav(pcm: np.ndarray, sample_rate: int) -> bytes:
    """Encode mono int16 PCM samples as a WAV byte string."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm.astype(np.int16).tobytes())
    return buf.getvalue()


async def transcribe(
    client: httpx.AsyncClient,
    wav_bytes: bytes,
    *,
    api_key: str,
    model: str = "whisper-large-v3",
    language: str = "fr",
    timeout: float = 30.0,
) -> Transcript:
    """POST audio to Groq Whisper and return the segmented transcript."""
    files = {"file": ("audio.wav", wav_bytes, "audio/wav")}
    data = {
        "model": model,
        "language": language,
        "response_format": "verbose_json",
        "temperature": "0",
    }
    headers = {"Authorization": f"Bearer {api_key}"}
    r = await client.post(
        f"{GROQ_BASE}/audio/transcriptions",
        headers=headers,
        files=files,
        data=data,
        timeout=timeout,
    )
    r.raise_for_status()
    return _parse_transcript(r.json())


async def prewarm(client: httpx.AsyncClient, *, api_key: str) -> None:
    """Warm the TLS + HTTP/2 connection to api.groq.com with a cheap GET."""
    with contextlib.suppress(httpx.HTTPError):
        await client.get(
            f"{GROQ_BASE}/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=5.0,
        )
