"""Macro engine: normalization, matching, expand/restore, storage, cleanup survival."""

from __future__ import annotations

import json
import os

import httpx
import pytest
import respx

from dicton import macros
from dicton.cleanup import cleanup
from dicton.config import CLEANUP_MODELS
from dicton.macros import Macro, expand, normalize, restore
from dicton.stt import GROQ_BASE

CRQPT = Macro(
    id="crqpt-url", spellings=["crqpt url", "crypte url", "CRQPT URL"], value="https://crqpt.com"
)
SIGNATURE = Macro(id="signature", spellings=["ma signature"], value="Cordialement,\nAsi0\n— alysis")


# ---- normalize ----


def test_normalize_case_accents_punctuation() -> None:
    assert normalize("CRQPT, URL !") == "crqpt url"
    assert normalize("  Crypté   URL  ") == "crypte url"
    assert normalize("l'URL") == "l url"
    assert normalize("ma-signature…") == "ma signature"


def test_normalize_empty_and_punctuation_only() -> None:
    assert normalize("") == ""
    assert normalize("…, !") == ""


# ---- expand: matching rules ----


def test_any_spelling_matches() -> None:
    for spoken in ["crqpt url", "crypte url", "CRQPT URL", "Crypté URL"]:
        tokenized, tok = expand(f"envoie le {spoken} au client", [CRQPT])
        assert len(tok) == 1, spoken
        assert restore(tokenized, tok) == "envoie le https://crqpt.com au client"
    # Punctuation glued to the trigger stays outside the token, in the
    # surrounding text (the cleanup pass owns it).
    tokenized, tok = expand("envoie le crqpt url. au client", [CRQPT])
    assert restore(tokenized, tok) == "envoie le https://crqpt.com. au client"


def test_word_boundaries_no_match_inside_word() -> None:
    url = Macro(id="u", spellings=["url"], value="X")
    tokenized, tok = expand("regarde urlencode et configurl", [url])
    assert tok == {}
    assert tokenized == "regarde urlencode et configurl"


def test_all_occurrences_replaced() -> None:
    raw = "crqpt url puis encore crqpt url"
    tokenized, tok = expand(raw, [CRQPT])
    assert len(tok) == 2
    assert restore(tokenized, tok) == "https://crqpt.com puis encore https://crqpt.com"


def test_longest_spelling_wins_on_overlap() -> None:
    short = Macro(id="s", spellings=["crqpt"], value="SHORT")
    tokenized, tok = expand("le crqpt url ici", [short, CRQPT])
    assert restore(tokenized, tok) == "le https://crqpt.com ici"


def test_dictation_is_only_the_trigger() -> None:
    tokenized, tok = expand("ma signature", [SIGNATURE])
    assert restore(tokenized, tok) == "Cordialement,\nAsi0\n— alysis"


def test_value_at_sentence_start_is_verbatim() -> None:
    tokenized, tok = expand("crqpt url est le lien", [CRQPT])
    assert restore(tokenized, tok) == "https://crqpt.com est le lien"


def test_no_macros_passthrough() -> None:
    assert expand("bonjour monde", []) == ("bonjour monde", {})
    assert expand("", [CRQPT]) == ("", {})


def test_match_across_punctuation_in_dictation() -> None:
    # Whisper may insert punctuation between trigger words; normalization eats it.
    tokenized, tok = expand("envoie le crqpt, url maintenant", [CRQPT])
    assert len(tok) == 1
    assert restore(tokenized, tok) == "envoie le https://crqpt.com maintenant"


# ---- restore: fallback ----


def test_restore_fallback_when_token_dropped() -> None:
    tokenized, tok = expand("envoie le crqpt url au client", [CRQPT])
    mangled = "Envoie le au client."  # the cleanup model ate the token
    out = restore(mangled, tok, fallback=tokenized)
    assert "https://crqpt.com" in out
    assert out == tokenized.replace(next(iter(tok)), "https://crqpt.com")


def test_restore_without_fallback_replaces_what_survives() -> None:
    tokenized, tok = expand("crqpt url et ma signature", [CRQPT, SIGNATURE])
    assert restore(tokenized, tok).startswith("https://crqpt.com et Cordialement,")


def test_restore_empty_token_map_is_identity() -> None:
    assert restore("texte propre", {}) == "texte propre"


# ---- storage ----


@pytest.fixture
def macros_file(tmp_path, monkeypatch):
    path = tmp_path / "macros.json"
    monkeypatch.setattr(macros, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(macros, "MACROS_PATH", path)
    monkeypatch.setattr(macros, "_cache", None)
    return path


def test_load_missing_file_returns_empty(macros_file) -> None:
    assert macros.load() == []


def test_save_load_round_trip(macros_file) -> None:
    macros.save([CRQPT, SIGNATURE])
    loaded = macros.load()
    assert loaded == [CRQPT, SIGNATURE]
    assert loaded[1].value == "Cordialement,\nAsi0\n— alysis"
    assert (os.stat(macros_file).st_mode & 0o777) == 0o600


def test_load_uses_mtime_cache(macros_file) -> None:
    macros.save([CRQPT])
    first = macros.load()
    assert macros.load() is first  # same mtime → cached object
    # Hand-edit the file with a strictly newer mtime → re-read.
    macros_file.write_text(json.dumps([{"id": "x", "spellings": ["x"], "value": "y"}]))
    st = os.stat(macros_file)
    os.utime(macros_file, (st.st_atime, st.st_mtime + 1))
    assert [m.id for m in macros.load()] == ["x"]


def test_load_corrupt_file_disables_macros(macros_file) -> None:
    macros_file.write_text("{not json")
    assert macros.load() == []
    macros_file.write_text(json.dumps([{"id": "a"}]))  # missing keys
    assert macros.load() == []


# ---- cleanup survival (mocked) ----


@pytest.mark.asyncio
@respx.mock
async def test_token_survives_cleanup_round_trip() -> None:
    tokenized, tok = expand("envoie le crqpt url au client", [CRQPT])
    token = next(iter(tok))
    respx.post(f"{GROQ_BASE}/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={"choices": [{"message": {"content": f"Envoie le {token} au client."}}]},
        )
    )
    async with httpx.AsyncClient(http2=False) as c:
        cleaned = await cleanup(c, tokenized, api_key="sk-test", model="m")
    assert restore(cleaned, tok, fallback=tokenized) == "Envoie le https://crqpt.com au client."


@pytest.mark.asyncio
@respx.mock
async def test_cleanup_drops_token_falls_back_to_tokenized() -> None:
    tokenized, tok = expand("envoie le crqpt url au client", [CRQPT])
    respx.post(f"{GROQ_BASE}/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={"choices": [{"message": {"content": "Envoie le lien au client."}}]},
        )
    )
    async with httpx.AsyncClient(http2=False) as c:
        cleaned = await cleanup(c, tokenized, api_key="sk-test", model="m")
    out = restore(cleaned, tok, fallback=tokenized)
    assert "https://crqpt.com" in out  # macro fired despite the dropped token


@pytest.mark.asyncio
@respx.mock
async def test_cleanup_http_error_keeps_tokenized_input() -> None:
    tokenized, tok = expand("crqpt url", [CRQPT])
    respx.post(f"{GROQ_BASE}/chat/completions").mock(return_value=httpx.Response(500))
    async with httpx.AsyncClient(http2=False) as c:
        cleaned = await cleanup(c, tokenized, api_key="sk-test", model="m")
    assert restore(cleaned, tok, fallback=tokenized) == "https://crqpt.com"


# ---- token survival against the real models (empirical validation) ----
# The placeholder scheme rests on cleanup models preserving the token chars.
# Run with a real key to validate: GROQ_API_KEY=… pytest -k real_models
@pytest.mark.skipif(not os.environ.get("GROQ_API_KEY"), reason="needs GROQ_API_KEY")
@pytest.mark.asyncio
@pytest.mark.parametrize("model", CLEANUP_MODELS)
async def test_token_survives_real_models(model: str) -> None:
    tokenized, tok = expand("envoie le crqpt url au client demain matin", [CRQPT])
    token = next(iter(tok))
    async with httpx.AsyncClient(http2=True) as c:
        cleaned = await cleanup(c, tokenized, api_key=os.environ["GROQ_API_KEY"], model=model)
    assert token in cleaned, f"{model} dropped the macro token: {cleaned!r}"
