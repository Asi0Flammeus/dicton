"""Voice-triggered text macros — spoken trigger → byte-exact value.

A Macro maps one or more *spellings* (known Whisper transcriptions of the
spoken trigger) to a verbatim replacement value. Detection is inline: every
dictation is scanned, no sentinel word. Matching is done on a normalized
form (casefold, no diacritics/punctuation, compacted spaces) at word
boundaries, longest spelling wins, all occurrences are replaced.

The value must never reach the cleanup LLM (it would paraphrase a URL or
reformat a block), so expansion happens in two steps around the cleanup:
``expand()`` swaps each match for an opaque token before cleanup and
``restore()`` swaps tokens back for the verbatim value afterwards — with a
fallback to the pre-cleanup text if the model dropped a token.

The editor window (`dicton macros`) and the daemon never talk to each other;
they only share ``macros.json``, re-read on every dictation via an mtime
cache.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import unicodedata
from dataclasses import asdict, dataclass

from .config import CONFIG_DIR

log = logging.getLogger("dicton")

MACROS_PATH = CONFIG_DIR / "macros.json"

# Token sentinels, chosen empirically against the 4 CLEANUP_MODELS (see
# test_token_survives_real_models): a bare opaque alphanumeric blob is the
# only form every model returns verbatim. Decorated forms (\u27e6M0\u27e7, [[M0]],
# {{M0}}, @@M0@@, __M0__, U+E000 private-use) all get their decoration
# stripped by at least one Llama model \u2014 but the inner alphanumeric run
# always survives, so the token IS only an alphanumeric run. restore()
# still has a fallback if a model mangles one anyway.
_TOK_OPEN = "QZM"
_TOK_CLOSE = "XQZ"


@dataclass
class Macro:
    id: str
    spellings: list[str]
    value: str


# ---- storage ----

_cache: tuple[float, list[Macro]] | None = None


def load() -> list[Macro]:
    """Read macros.json, cached on mtime so the daemon can call this on every
    dictation without re-parsing. Missing or corrupt file → no macros."""
    global _cache
    try:
        mtime = MACROS_PATH.stat().st_mtime
    except OSError:
        _cache = None
        return []
    if _cache is not None and _cache[0] == mtime:
        return _cache[1]
    try:
        raw = json.loads(MACROS_PATH.read_text(encoding="utf-8"))
        macros = [
            Macro(
                id=str(d["id"]), spellings=[str(s) for s in d["spellings"]], value=str(d["value"])
            )
            for d in raw
        ]
    except (OSError, ValueError, KeyError, TypeError):
        log.warning("macros.json is unreadable — macros disabled until fixed")
        _cache = None
        return []
    _cache = (mtime, macros)
    return macros


def save(macros: list[Macro]) -> None:
    global _cache
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    body = json.dumps([asdict(m) for m in macros], ensure_ascii=False, indent=2)
    MACROS_PATH.write_text(body + "\n", encoding="utf-8")
    with contextlib.suppress(OSError):
        os.chmod(MACROS_PATH, 0o600)
    _cache = None


# ---- matching ----


def normalize(s: str) -> str:
    """Casefold, strip diacritics, drop punctuation, compact spaces."""
    folded = unicodedata.normalize("NFKD", s.casefold())
    kept = (ch if ch.isalnum() else " " for ch in folded if not unicodedata.combining(ch))
    return " ".join("".join(kept).split())


def _words(raw: str) -> list[tuple[int, int, str]]:
    """Words of ``raw`` as (start, end, normalized) with raw-text offsets, so a
    match found on normalized words can be spliced out of the raw text."""
    words: list[tuple[int, int, str]] = []
    start = -1
    end = -1
    buf: list[str] = []
    for i, ch in enumerate(raw):
        norm = "".join(
            c for c in unicodedata.normalize("NFKD", ch.casefold()) if not unicodedata.combining(c)
        )
        if norm and all(c.isalnum() for c in norm):
            if start < 0:
                start = i
            buf.append(norm)
            end = i + 1
        elif start >= 0:
            words.append((start, end, "".join(buf)))
            start, buf = -1, []
    if start >= 0:
        words.append((start, end, "".join(buf)))
    return words


def expand(raw: str, macros: list[Macro]) -> tuple[str, dict[str, str]]:
    """Replace every spelling match in ``raw`` with an opaque token.

    Returns the tokenized text plus the token → value map for ``restore()``.
    Matching is word-boundary on normalized words; at each position the
    longest matching spelling wins (avoids partial shadowing between macros).
    """
    if not raw or not macros:
        return raw, {}
    table: dict[tuple[str, ...], str] = {}
    for m in macros:
        for sp in m.spellings:
            key = tuple(normalize(sp).split())
            if key:
                table.setdefault(key, m.value)
    if not table:
        return raw, {}

    words = _words(raw)
    max_words = max(len(k) for k in table)
    out: list[str] = []
    token_map: dict[str, str] = {}
    pos = 0
    i = 0
    while i < len(words):
        matched = 0
        for n in range(min(max_words, len(words) - i), 0, -1):
            if tuple(w[2] for w in words[i : i + n]) in table:
                matched = n
                break
        if matched:
            start, end = words[i][0], words[i + matched - 1][1]
            token = f"{_TOK_OPEN}M{len(token_map)}{_TOK_CLOSE}"
            token_map[token] = table[tuple(w[2] for w in words[i : i + matched])]
            out.append(raw[pos:start])
            out.append(token)
            pos = end
            i += matched
        else:
            i += 1
    out.append(raw[pos:])
    return "".join(out), token_map


def validate(
    spellings: list[str],
    value: str,
    macros: list[Macro],
    current: Macro | None,
) -> tuple[list[str], list[str]]:
    """Check an edited macro. Returns (errors, warnings): errors block the
    save (empty trigger/value, spelling that normalizes to nothing), warnings
    only need confirmation (spelling already used by another macro — the
    first one would silently win at match time)."""
    errors: list[str] = []
    warnings: list[str] = []
    if not any(normalize(s) for s in spellings):
        errors.append("Au moins une orthographe (non vide) est requise.")
    if not value:
        errors.append("La valeur est vide.")
    for s in spellings:
        if s.strip() and not normalize(s):
            errors.append(f"« {s} » ne contient aucun mot reconnaissable.")
    own = {normalize(s) for s in spellings if normalize(s)}
    for m in macros:
        if current is not None and m.id == current.id:
            continue
        for s in m.spellings:
            if normalize(s) in own:
                warnings.append(f"« {s} » est déjà utilisée par la macro « {m.id} ».")
    return errors, warnings


def restore(text: str, token_map: dict[str, str], *, fallback: str | None = None) -> str:
    """Swap tokens back for their verbatim values.

    If the cleanup model dropped any token, the cleaned text can no longer be
    trusted to carry the macro: discard it and restore on ``fallback`` (the
    pre-cleanup tokenized text) instead — the macro still fires, at the cost
    of the polish pass. Feature reliability beats polish.
    """
    if not token_map:
        return text
    if fallback is not None and any(tok not in text for tok in token_map):
        log.warning("cleanup dropped a macro token — restoring on pre-cleanup text")
        text = fallback
    for token, value in token_map.items():
        text = text.replace(token, value)
    return text
