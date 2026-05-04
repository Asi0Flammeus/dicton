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


# Pinned low-latency cleaner model per provider. Used when the caller does
# not pin one explicitly, and ALWAYS used for non-primary fallback providers
# (so a Gemini→Anthropic fallback doesn't ship a Gemini model id to the
# Anthropic SDK).
_DEFAULT_CLEANER_MODELS: dict[str, str] = {
    "gemini": "gemini-flash-lite-latest",
    "anthropic": "claude-haiku-4-5-20251001",
}


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
    model: str | None = None,
    timeout_s: float = 8.0,  # noqa: ARG001 - reserved for future per-call timeout wiring
    debug: bool = False,
) -> str | None:
    """Clean a raw STT transcript via a pinned low-latency LLM.

    Model selection rules:

    * ``user_provider`` (e.g. ``"gemini"``) selects the primary provider; the
      fallback chain is ``[primary] + [other registered providers]``.
    * ``model`` is an **explicit override for the primary provider only**. It
      is intentionally NOT propagated to fallback providers — passing a
      Gemini model id to the Anthropic SDK fails with a 400 error and the
      cleaner would simply give up.
    * For any non-primary fallback (and for the primary when ``model`` is
      ``None``/empty), the cleaner uses the per-provider default from
      :data:`_DEFAULT_CLEANER_MODELS`.
    * ``user_provider="auto"`` ignores ``model`` and uses the per-provider
      defaults across the whole chain.

    Returns the cleaned text on success, the literal string ``"None"`` if the
    LLM judges the input meaningless, or ``None`` on any failure (so the
    caller can fall open to the raw STT text).
    """
    if not text:
        return None

    _register_providers()

    user_provider = (user_provider or "auto").lower()
    if user_provider and user_provider != "auto":
        primary: str | None = user_provider
        order = [user_provider] + [p for p in DEFAULT_FALLBACK_ORDER if p != user_provider]
    else:
        primary = None
        order = list(DEFAULT_FALLBACK_ORDER)

    primary_model_override = (model or "").strip() or None
    prompt = _build_prompt(text, language)

    last_error: Exception | None = None
    for name in order:
        provider = get_llm_provider(name)
        if not provider.is_available():
            continue
        if primary is not None and name == primary and primary_model_override:
            per_call_model = primary_model_override
        else:
            per_call_model = _DEFAULT_CLEANER_MODELS.get(name)
        try:
            result = provider.complete(prompt, model=per_call_model)
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
