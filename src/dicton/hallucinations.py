"""Deterministic stripper for known Whisper hallucinations.

Whisper was trained on TV-subtitle corpora and reliably hallucinates a small
set of canned phrases (subtitle credits, sign-off boilerplate, "abonnez-vous"
nags) on silence or low-SNR audio. Cheaper and more reliable to scrub these
deterministically before the LLM cleanup pass than to ask the LLM to do it.

Patterns target French Whisper output. Each pattern is anchored to whole
phrases so we never chew into legitimate dictation.
"""

from __future__ import annotations

import re

_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"sous-titrage\s+(?:de\s+la\s+)?soci[ée]t[ée]\s+radio-canada\.?", re.I),
    re.compile(
        r"sous-titres?\s+(?:r[ée]alis[ée]s?\s+)?par\s+(?:la\s+)?communaut[ée]\s+d['’]?amara\.org\.?",
        re.I,
    ),
    re.compile(r"sous-titres?\s+(?:r[ée]alis[ée]s?\s+)?par\s+[^\n]{0,80}?\.org\.?", re.I),
    re.compile(r"sous-titres?\s+(?:r[ée]alis[ée]s?\s+)?par\s+[^\n.]{0,60}\.?", re.I),
    re.compile(r"❤️?\s*par\s+soustitreur\.com\.?", re.I),
    re.compile(r"merci\s+d['’]?avoir\s+regard[ée]\s+(?:cette\s+vid[ée]o|la\s+vid[ée]o)\.?", re.I),
    re.compile(r"n['’]?oubliez\s+pas\s+de\s+vous\s+abonner\.?", re.I),
    re.compile(r"abonnez-vous\s+(?:à\s+(?:la\s+)?chaîne|et\s+activez[^\n.]{0,40})?\.?", re.I),
    re.compile(
        r"merci\s+(?:beaucoup\s+)?(?:à\s+(?:tous|vous)|d['’]avoir\s+(?:écouté|regardé))\.?", re.I
    ),
    re.compile(r"musique\s+(?:de\s+fin|d['’]?intro)\.?", re.I),
    re.compile(r"\[\s*(?:musique|applaudissements|silence)\s*\]", re.I),
)


def strip_hallucinations(text: str) -> str:
    """Remove known Whisper boilerplate hallucinations from a transcript.

    Returns the input unchanged if nothing matches. Collapses the runs of
    whitespace that a removal can leave behind.
    """
    if not text:
        return text
    out = text
    for pat in _PATTERNS:
        out = pat.sub(" ", out)
    out = re.sub(r"[ \t]{2,}", " ", out)
    out = re.sub(r"\s+([.,;:!?])", r"\1", out)
    return out.strip()
