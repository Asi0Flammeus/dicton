"""LLM Processor for Dicton - Multi-provider API integration for text manipulation

This module provides LLM-powered text processing for:
- Act on Text: Apply voice instructions to selected text
- Reformulation: Clean up and lightly reformat transcribed text
- Translation: Translate text to target language

Supports both Gemini and Anthropic (Haiku) with automatic fallback.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .config import config

if TYPE_CHECKING:
    from .context_detector import ContextInfo

# Lazy imports to avoid loading libraries unless needed
_genai_client = None
_anthropic_client = None


# =============================================================================
# Client Initialization
# =============================================================================


def _get_gemini_client():
    """Get or create the Gemini client (lazy initialization)."""
    global _genai_client

    if _genai_client is not None:
        return _genai_client

    if not config.GEMINI_API_KEY:
        return None

    try:
        from google import genai

        _genai_client = genai.Client(api_key=config.GEMINI_API_KEY)
        return _genai_client
    except ImportError:
        return None


def _get_anthropic_client():
    """Get or create the Anthropic client (lazy initialization)."""
    global _anthropic_client

    if _anthropic_client is not None:
        return _anthropic_client

    if not config.ANTHROPIC_API_KEY:
        return None

    try:
        import anthropic

        _anthropic_client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        return _anthropic_client
    except ImportError:
        return None


# =============================================================================
# Provider-specific implementations
# =============================================================================


def _call_gemini(prompt: str) -> str | None:
    """Call Gemini API with the given prompt."""
    client = _get_gemini_client()
    if client is None:
        return None

    try:
        from google.genai import types

        response = client.models.generate_content(
            model=config.GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                http_options=types.HttpOptions(timeout=int(config.API_TIMEOUT * 1000)),
            ),
        )
        if response.text:
            return response.text.strip()
        return None
    except Exception as e:
        if config.DEBUG:
            print(f"Gemini error: {e}")
        raise


def _call_anthropic(prompt: str) -> str | None:
    """Call Anthropic API with the given prompt."""
    client = _get_anthropic_client()
    if client is None:
        return None

    try:
        message = client.messages.create(
            model=config.ANTHROPIC_MODEL,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
            timeout=config.API_TIMEOUT,
        )
        if message.content and len(message.content) > 0:
            return message.content[0].text.strip()
        return None
    except Exception as e:
        if config.DEBUG:
            print(f"Anthropic error: {e}")
        raise


def _call_llm_with_fallback(prompt: str) -> str | None:
    """Call LLM with configured provider, falling back to alternative on error.

    Uses the provider configured in LLM_PROVIDER first. If that fails and the
    alternative provider is configured, tries that as fallback.
    """
    primary = config.LLM_PROVIDER
    providers = {
        "gemini": (_call_gemini, _get_gemini_client),
        "anthropic": (_call_anthropic, _get_anthropic_client),
    }

    # Determine order of providers to try
    if primary == "anthropic":
        order = ["anthropic", "gemini"]
    else:
        order = ["gemini", "anthropic"]

    last_error = None

    for provider_name in order:
        call_fn, get_client_fn = providers[provider_name]

        # Skip if this provider isn't configured
        if get_client_fn() is None:
            continue

        try:
            result = call_fn(prompt)
            if result is not None:
                return result
        except Exception as e:
            last_error = e
            if config.DEBUG:
                print(f"{provider_name} failed, trying fallback: {e}")
            continue

    # All providers failed
    if last_error and config.DEBUG:
        print(f"All LLM providers failed. Last error: {last_error}")

    return None


# =============================================================================
# Context-Aware Prompts
# =============================================================================


def _build_context_preamble(context: ContextInfo | None) -> str:
    """Build a context-aware preamble for LLM prompts.

    Retrieves the matching profile's llm_preamble and formats it for injection
    at the start of prompts.

    Args:
        context: The detected context information, or None.

    Returns:
        A formatted preamble string, or empty string if no context.
    """
    if context is None:
        return ""

    # Import here to avoid circular imports
    from .context_profiles import get_profile_manager

    manager = get_profile_manager()
    profile = manager.match_context(context)

    if config.CONTEXT_DEBUG:
        print(f"[Context] App: {context.app_name}, Profile: {profile.name if profile else 'default'}")
        if context.window:
            print(f"[Context] Window: {context.window.title} ({context.window.wm_class})")
        if context.widget:
            print(f"[Context] Widget: {context.widget.role} - {context.widget.name}")

    if profile and profile.llm_preamble:
        if config.CONTEXT_DEBUG:
            print(f"[Context] Preamble: {profile.llm_preamble[:50]}...")
        return f"CONTEXT: {profile.llm_preamble}\n\n"

    return ""


# =============================================================================
# Public API
# =============================================================================


def act_on_text(
    selected_text: str,
    instruction: str,
    context: ContextInfo | None = None,
) -> str | None:
    """Apply a voice instruction to selected text using LLM.

    Args:
        selected_text: The text the user has selected.
        instruction: The voice instruction (e.g., "make this more formal").
        context: Optional context information for context-aware processing.

    Returns:
        The modified text, or None on error.
    """
    if not selected_text or not instruction:
        return None

    context_preamble = _build_context_preamble(context)

    prompt = f"""{context_preamble}You are a text manipulation assistant. Apply the user's instruction to the provided text.

IMPORTANT RULES:
1. Return ONLY the modified text, no explanations or commentary
2. Preserve the original formatting (paragraphs, line breaks, etc.) unless the instruction requires changing it
3. Maintain the original language unless translation is requested
4. Apply the instruction precisely as stated

SELECTED TEXT:
{selected_text}

USER INSTRUCTION:
{instruction}

MODIFIED TEXT:"""

    return _call_llm_with_fallback(prompt)


def reformulate(
    text: str,
    language: str | None = None,
    context: ContextInfo | None = None,
) -> str | None:
    """Lightly reformulate text to clean up grammar and filler words.

    Args:
        text: The transcribed text to reformulate.
        language: Optional language code (e.g., 'en', 'fr') to ensure output matches.
        context: Optional context information for context-aware processing.

    Returns:
        The reformulated text, or None on error.
    """
    if not text:
        return None

    language_instruction = ""
    if language:
        language_instruction = f"The text is in {language}. Keep your output in the same language."

    context_preamble = _build_context_preamble(context)

    prompt = f"""{context_preamble}You are a text cleanup assistant. Lightly reformulate the following transcribed speech.

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

    result = _call_llm_with_fallback(prompt)
    if result and result.strip().lower() == "none":
        return None
    return result


def translate(
    text: str,
    target_language: str = "English",
    context: ContextInfo | None = None,
) -> str | None:
    """Translate text to target language.

    Uses explicit two-step process:
    1. CLEAN: Remove all filler words (mandatory)
    2. TRANSLATE: Translate the cleaned text

    Args:
        text: The text to translate.
        target_language: The language to translate to (default: English).
        context: Optional context information for context-aware processing.

    Returns:
        The translated text, or None on error.
    """
    if not text:
        return None

    context_preamble = _build_context_preamble(context)

    prompt = f"""{context_preamble}You are a translator. Your task has TWO MANDATORY STEPS.

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

    result = _call_llm_with_fallback(prompt)
    if result and result.strip().lower() == "none":
        return None
    return result


def is_available() -> bool:
    """Check if LLM processing is available (at least one provider configured)."""
    # Check Gemini
    if config.GEMINI_API_KEY:
        try:
            from google import genai  # noqa: F401

            return True
        except ImportError:
            pass

    # Check Anthropic
    if config.ANTHROPIC_API_KEY:
        try:
            import anthropic  # noqa: F401

            return True
        except ImportError:
            pass

    return False


def get_available_providers() -> list[str]:
    """Get list of available LLM providers."""
    providers = []

    if config.GEMINI_API_KEY:
        try:
            from google import genai  # noqa: F401

            providers.append("gemini")
        except ImportError:
            pass

    if config.ANTHROPIC_API_KEY:
        try:
            import anthropic  # noqa: F401

            providers.append("anthropic")
        except ImportError:
            pass

    return providers
