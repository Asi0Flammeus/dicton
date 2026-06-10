"""Macros editor logic — CRUD helpers, validation, spelling capture wiring.

The Qt window itself is not instantiated here; everything it delegates to
(id generation, upsert/remove, validate, record → raw STT) is plain Python.
"""

from __future__ import annotations

import httpx
import numpy as np
import pytest
import respx

from dicton import macros_ui
from dicton.config import Config
from dicton.macros import Macro, validate
from dicton.macros_ui import Recorder, new_macro_id, remove, transcribe_spelling, upsert
from dicton.stt import GROQ_BASE

CRQPT = Macro(id="crqpt-url", spellings=["crqpt url"], value="https://crqpt.com")
SIGNATURE = Macro(id="signature", spellings=["ma signature"], value="Cordialement")


# ---- id generation ----


def test_new_macro_id_slugs_the_spelling() -> None:
    assert new_macro_id("CRQPT, URL !", set()) == "crqpt-url"


def test_new_macro_id_uniquifies() -> None:
    assert new_macro_id("crqpt url", {"crqpt-url"}) == "crqpt-url-2"
    assert new_macro_id("crqpt url", {"crqpt-url", "crqpt-url-2"}) == "crqpt-url-3"


def test_new_macro_id_falls_back_to_uuid_on_empty() -> None:
    generated = new_macro_id("…!", set())
    assert len(generated) == 8


# ---- upsert / remove ----


def test_upsert_appends_new_macro() -> None:
    assert upsert([CRQPT], SIGNATURE) == [CRQPT, SIGNATURE]


def test_upsert_replaces_same_id() -> None:
    edited = Macro(id="crqpt-url", spellings=["crqpt url", "crypte url"], value="https://crqpt.com")
    out = upsert([CRQPT, SIGNATURE], edited)
    assert out == [edited, SIGNATURE]


def test_remove_by_id() -> None:
    assert remove([CRQPT, SIGNATURE], "crqpt-url") == [SIGNATURE]
    assert remove([CRQPT], "unknown") == [CRQPT]


# ---- validation ----


def test_validate_requires_spelling_and_value() -> None:
    errors, _ = validate([], "", [], None)
    assert len(errors) == 2
    errors, _ = validate(["  "], "x", [], None)
    assert len(errors) == 1


def test_validate_rejects_unmatchable_spelling() -> None:
    errors, _ = validate(["crqpt url", "…!"], "v", [], None)
    assert any("…!" in e for e in errors)


def test_validate_warns_on_duplicate_spelling_across_macros() -> None:
    errors, warnings = validate(["CRQPT URL."], "v", [CRQPT, SIGNATURE], None)
    assert errors == []
    assert len(warnings) == 1
    assert "crqpt-url" in warnings[0]


def test_validate_ignores_own_macro_for_duplicates() -> None:
    errors, warnings = validate(["crqpt url"], "v", [CRQPT], CRQPT)
    assert errors == []
    assert warnings == []


# ---- spelling capture ----


@pytest.mark.asyncio
@respx.mock
async def test_transcribe_spelling_returns_raw_text() -> None:
    respx.post(f"{GROQ_BASE}/audio/transcriptions").mock(
        return_value=httpx.Response(
            200,
            json={
                "text": "crypte url",
                "segments": [
                    {
                        "text": " crypte url",
                        # Raw means raw: a segment the hallucination filter
                        # would drop must still come through as a spelling.
                        "no_speech_prob": 0.95,
                        "avg_logprob": -1.2,
                        "compression_ratio": 0.8,
                    }
                ],
            },
        )
    )
    cfg = Config(groq_api_key="sk-test")
    import asyncio

    text = await asyncio.to_thread(transcribe_spelling, cfg, b"WAVE")
    assert text == "crypte url"


def test_recorder_collects_frames_into_wav(monkeypatch) -> None:
    class FakeStream:
        def __init__(self, *, callback, **kwargs):
            self.callback = callback

        def start(self):
            frame = np.ones((160, 1), dtype=np.int16)
            self.callback(frame, 160, None, None)
            self.callback(frame * 2, 160, None, None)

        def stop(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(macros_ui.sd, "InputStream", FakeStream)
    rec = Recorder(16000, None)
    wav = rec.stop()
    assert wav[:4] == b"RIFF"
    assert len(wav) > 44 + 2 * 320 - 1  # header + 320 samples of int16
