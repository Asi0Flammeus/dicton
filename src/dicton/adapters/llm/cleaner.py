"""Pre-output transcript cleaner.

Sits between STT and the mode-specific text processing.  Removes filler
words, strips bracketed non-speech annotations, and repairs grammar while
preserving lexical content, tone, and language.

Intentionally fail-open: any unexpected condition (provider unavailable,
network error, exception) returns ``None`` so the caller keeps the raw
STT text.  The literal string ``"None"`` is preserved as the LLM's
""no meaningful speech"" sentinel.
"""

from __future__ import annotations

import logging

from .factory import DEFAULT_FALLBACK_ORDER, _register_providers, get_llm_provider

logger = logging.getLogger(__name__)


_CLEANER_PROMPT_TEMPLATE = """You are a transcript cleaner. The input is raw speech-to-text output.

YOUR JOB:
- Remove filler words and hesitation sounds in any language
  (euh, heu, um, uh, like, you know, en fait, du coup, voilà, genre, bah, ben, hein, …).
- Remove ALL bracketed or parenthesised non-speech annotations the STT may have
  emitted: [bruit], [noise], [music], [silence], [inaudible], (rires), (laughs), …
- Repair grammar and syntax so the output is a well-formed sentence (or several),
  in the SAME language as the input.
- Preserve faithfully WHAT was said: do not paraphrase, do not summarise, do not
  add ideas, do not change the tone or register, do not translate.
- Keep proper nouns, technical terms, code identifiers verbatim.
- Light punctuation only (commas, periods, question marks). No reformatting into
  lists, no markdown.
- If the input is empty, only static, or has no meaningful speech, output
  exactly: None
{language_instruction}
OUTPUT: only the cleaned text, nothing else.

INPUT:
{text}

CLEANED:"""


def _build_prompt(text: str, language: str | None) -> str:
    language_instruction = ""
    if language and language.lower() != "auto":
        language_instruction = (
            f"\nThe input language is {language}. Keep the cleaned output in the same language.\n"
        )
    return _CLEANER_PROMPT_TEMPLATE.format(text=text, language_instruction=language_instruction)


def clean_transcript(
    text: str,
    *,
    language: str | None = None,
    user_provider: str = "gemini",
    model: str | None = "gemini-flash-lite-latest",
    timeout_s: float = 8.0,  # noqa: ARG001 - reserved for future per-call timeout wiring
    debug: bool = False,
) -> str | None:
    """Clean a raw STT transcript via a pinned low-latency LLM.

    Returns the cleaned text on success, the literal string ``"None"`` if the
    LLM judges the input meaningless, or ``None`` on any failure (so the
    caller can fall open to the raw STT text).
    """
    if not text:
        return None

    _register_providers()

    user_provider = (user_provider or "auto").lower()
    if user_provider and user_provider != "auto":
        order = [user_provider] + [p for p in DEFAULT_FALLBACK_ORDER if p != user_provider]
    else:
        order = list(DEFAULT_FALLBACK_ORDER)

    prompt = _build_prompt(text, language)

    last_error: Exception | None = None
    for name in order:
        provider = get_llm_provider(name)
        if not provider.is_available():
            continue
        try:
            result = provider.complete(prompt, model=model)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if debug:
                print(f"transcript cleaner: {name} failed, trying fallback: {exc}")
            continue
        if result is None:
            continue
        return result.strip()

    if last_error is not None:
        logger.warning("transcript cleaner failed on all providers: %s", last_error)
    return None
