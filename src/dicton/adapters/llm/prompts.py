"""LLM-powered text operations: reformulate, translate."""

from __future__ import annotations

from .factory import DEFAULT_FALLBACK_ORDER, _register_providers, get_llm_provider


def _call(
    prompt: str,
    *,
    user_provider: str = "auto",
    debug: bool = False,
) -> str | None:
    """Call the configured LLM provider, falling back on error."""
    _register_providers()

    user_provider = user_provider.lower()
    if user_provider and user_provider != "auto":
        order = [user_provider] + [p for p in DEFAULT_FALLBACK_ORDER if p != user_provider]
    else:
        order = list(DEFAULT_FALLBACK_ORDER)

    last_error = None
    for name in order:
        provider = get_llm_provider(name)
        if not provider.is_available():
            continue
        try:
            result = provider.complete(prompt)
            if result is not None:
                return result
        except Exception as e:
            last_error = e
            if debug:
                print(f"{name} failed, trying fallback: {e}")

    if last_error and debug:
        print(f"All LLM providers failed. Last error: {last_error}")

    return None


def reformulate(
    text: str,
    language: str | None = None,
    *,
    user_provider: str = "auto",
    debug: bool = False,
) -> str | None:
    """Lightly reformulate text to clean up grammar and filler words.

    Args:
        text: The transcribed text to reformulate.
        language: Optional language code (e.g., 'en', 'fr') to ensure output matches.
        user_provider: Preferred LLM provider name.
        debug: Enable debug output.

    Returns:
        The reformulated text, or None on error.
    """
    if not text:
        return None

    language_instruction = ""
    if language:
        language_instruction = f"The text is in {language}. Keep your output in the same language."

    prompt = f"""You are a structural text reformulator. The input has already been
cleaned of filler words and STT artefacts upstream — focus on structure, not
filler removal.

RULES:
1. OUTPUT MUST BE IN THE SAME LANGUAGE as the input. DO NOT translate.
2. Preserve the speaker's voice, tone, and meaning. Keep changes minimal.
3. Convert spoken numbers to digits (e.g., "twenty-three" → "23",
   "vingt-trois" → "23").
4. Format enumerated items as lists when the speaker introduces points
   sequentially. Use numbered lists (1. 2. 3.) when speaker uses ordinals
   like "first", "second", "premier", "deuxième"; bullet points otherwise.
5. Interpret dictation commands and replace them with actual punctuation:
   - "new line" / "à la ligne" → line break
   - "new paragraph" / "nouveau paragraphe" → double line break
   - "dash" / "tiret" → "-"
   - "open parenthesis" / "ouvrir parenthèse" → "("
   - "close parenthesis" / "fermer parenthèse" → ")"
   - "open bracket" / "ouvrir crochet" → "["
   - "close bracket" / "fermer crochet" → "]"
   - "colon" / "deux points" → ":"
   - "semicolon" / "point virgule" → ";"
   - "comma" / "virgule" → ","
   - "period" / "point final" → "."
   - "question mark" / "point d'interrogation" → "?"
   - "exclamation mark" / "point d'exclamation" → "!"
6. If the input is empty or has no meaningful content, output exactly "None".
7. Return ONLY the reformulated text, no explanations.
{language_instruction}

TEXT:
{text}

REFORMULATED:"""

    result = _call(prompt, user_provider=user_provider, debug=debug)
    if result and result.strip().lower() == "none":
        return None
    return result


def translate(
    text: str,
    target_language: str = "English",
    *,
    user_provider: str = "auto",
    debug: bool = False,
) -> str | None:
    """Translate text to target language.

    Filler removal is done upstream by the transcript cleaner; this prompt
    focuses on translation only.

    Args:
        text: The text to translate.
        target_language: The language to translate to (default: English).
        user_provider: Preferred LLM provider name.
        debug: Enable debug output.

    Returns:
        The translated text, or None on error.
    """
    if not text:
        return None

    prompt = f"""You are a translator. Translate the input to {target_language}.

The input has already been cleaned upstream (filler words and STT artefacts
removed) — focus on producing an accurate, natural translation.

RULES:
- Provide an accurate, natural translation to {target_language}.
- Preserve the original tone and style.
- Convert spoken numbers to digits where the input still has them spelled out.
- Format enumerated items as lists: numbered (1. 2. 3.) for ordinals,
  bullet points otherwise.
- Interpret remaining dictation commands ("new line" → line break,
  "dash" → "-", etc.).
- Return ONLY the translated text, no explanations.
- If the input is empty or has no meaningful content, output exactly "None".

TEXT TO TRANSLATE:
{text}

TRANSLATION:"""

    result = _call(prompt, user_provider=user_provider, debug=debug)
    if result and result.strip().lower() == "none":
        return None
    return result
