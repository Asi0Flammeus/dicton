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
import time

from .factory import DEFAULT_FALLBACK_ORDER, _register_providers, get_llm_provider

logger = logging.getLogger(__name__)


# Pinned low-latency cleaner model per provider. Single source of truth for
# cleaner model IDs — keep in sync with adapters.llm.gemini.DEFAULT_GEMINI_MODEL.
# Used when the caller does not pin one explicitly, and ALWAYS used for
# non-primary fallback providers (so a Gemini→Anthropic fallback doesn't ship
# a Gemini model id to the Anthropic SDK).
_DEFAULT_CLEANER_MODELS: dict[str, str] = {
    "gemini": "gemini-flash-lite-latest",
    "anthropic": "claude-haiku-4-5-20251001",
}


_CLEANER_PROMPT_TEMPLATE = """Clean this speech-to-text transcript. Output ONLY the cleaned text.

Rules:
- Same language as input. Never translate.
- Remove filler words (euh, um, like, du coup, genre, …) and bracketed
  STT annotations ([bruit], [music], (rires), …).
- Fix grammar/syntax. Keep meaning, tone, proper nouns, technical terms.
- Light punctuation only.
- If empty or meaningless: output exactly None.

INPUT:
{text}"""


def _build_prompt(text: str, language: str | None) -> str:  # noqa: ARG001
    return _CLEANER_PROMPT_TEMPLATE.format(text=text)


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
    tried: list[str] = []
    for name in order:
        provider = get_llm_provider(name)
        if not provider.is_available():
            tried.append(f"{name}:unavailable")
            continue
        if primary is not None and name == primary and primary_model_override:
            per_call_model = primary_model_override
        else:
            per_call_model = _DEFAULT_CLEANER_MODELS.get(name)
        logger.info("transcript cleaner: trying %s (%s)", name, per_call_model or "<default>")
        if debug:
            print(f"🧹 transcript cleaner: {name} ({per_call_model or '<default>'})")
        started = time.monotonic()
        try:
            result = provider.complete(prompt, model=per_call_model)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            tried.append(f"{name}:error")
            if debug:
                print(f"🧹 transcript cleaner: {name} failed, trying fallback: {exc}")
            logger.warning("transcript cleaner %s raised: %s", name, exc)
            continue
        elapsed_ms = (time.monotonic() - started) * 1000
        if result is None:
            tried.append(f"{name}:no-result")
            continue
        cleaned = result.strip()
        logger.info(
            "transcript cleaner: %s/%s ok in %.0fms (%d→%d chars)",
            name,
            per_call_model or "<default>",
            elapsed_ms,
            len(text),
            len(cleaned),
        )
        if debug:
            print(
                f"🧹 transcript cleaner: {name} ok in {elapsed_ms:.0f}ms "
                f"({len(text)}→{len(cleaned)} chars)"
            )
        return cleaned

    if last_error is not None:
        logger.warning(
            "transcript cleaner failed on all providers (tried=%s): %s",
            tried,
            last_error,
        )
    else:
        logger.info("transcript cleaner skipped: no provider available (tried=%s)", tried)
    return None
