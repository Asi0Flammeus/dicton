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

    prompt = f"""You are a text cleanup assistant. Lightly reformulate the following transcribed speech.

IMPORTANT RULES:
1. FIRST: Detect the language of the input text
2. OUTPUT MUST BE IN THE SAME LANGUAGE as the input (French stays French, English stays English, etc.)
3. Remove filler words (um, uh, like, you know, euh, genre, en fait, etc.)
4. Fix minor grammar issues
5. DO NOT change the meaning or tone
6. DO NOT translate - keep the original language
7. Preserve the speaker's voice and style
8. Keep changes to the strict minimum to stay as close to the original
9. Return ONLY the cleaned text, no explanations
10. Convert spoken numbers to digits (e.g., "twenty-three" → "23", "three hundred" → "300", "vingt-trois" → "23")
11. Format enumerated items as lists when the speaker introduces points sequentially. Use numbered lists (1. 2. 3.) when speaker uses ordinals like "first", "second", "premier", "deuxième", or bullet points for other enumerations
12. If the input is empty, contains only static noise, or has no meaningful speech content, output exactly "None" with nothing else
13. Interpret dictation commands and replace them with actual punctuation/formatting:
    - "new line" / "à la ligne" → actual line break
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
{language_instruction}

TEXT TO CLEAN:
{text}

CLEANED TEXT (same language as input):"""

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

    Uses explicit two-step process:
    1. CLEAN: Remove all filler words (mandatory)
    2. TRANSLATE: Translate the cleaned text

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

    prompt = f"""You are a translator. Your task has TWO MANDATORY STEPS.

═══════════════════════════════════════════════════════════════════════════════
STEP 1 - CLEAN (MANDATORY): Remove ALL filler words before translating
═══════════════════════════════════════════════════════════════════════════════

You MUST remove every single instance of these filler words/phrases. This step is NOT optional.

FRENCH FILLERS (remove all of these):
- euh, heu, bah, bon, ben
- genre, en fait, du coup, voilà, quoi
- tu vois, tu sais, enfin, bref
- donc voilà, c'est-à-dire, comment dire
- ah, oh, ouais, hein, nan, mouais
- donc, alors, en gros, style
- j'veux dire, disons, enfin bref

ENGLISH FILLERS (remove all of these):
- um, uh, erm, hmm
- like, you know, I mean
- so, basically, actually
- kind of, sort of, kinda, sorta
- well, right, okay so
- I guess, you see, let's see
- and stuff, or whatever, or something

Also fix in Step 1:
- Grammar issues from speech
- Convert spoken numbers to digits ("vingt-trois" → "23", "three hundred" → "300")
- Interpret dictation commands (new line → actual line break, dash → "-", etc.)

═══════════════════════════════════════════════════════════════════════════════
STEP 2 - TRANSLATE: Translate the cleaned text to {target_language}
═══════════════════════════════════════════════════════════════════════════════

After cleaning, translate with these rules:
- Provide an accurate, natural translation to {target_language}
- Preserve the original tone and style
- Format enumerated items as lists: numbered (1. 2. 3.) for ordinals, bullet points otherwise
- Keep the translation close to the original meaning while being natural

═══════════════════════════════════════════════════════════════════════════════
OUTPUT RULES
═══════════════════════════════════════════════════════════════════════════════

- Return ONLY the final translated text, no explanations or step annotations
- Do NOT include any filler words in your output
- If the input is empty, contains only static noise, or has no meaningful speech content, output exactly "None"

TEXT TO TRANSLATE:
{text}

TRANSLATION:"""

    result = _call(prompt, user_provider=user_provider, debug=debug)
    if result and result.strip().lower() == "none":
        return None
    return result
