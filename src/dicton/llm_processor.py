"""LLM Processor for Dicton - Gemini API integration for text manipulation

This module provides LLM-powered text processing for:
- Act on Text: Apply voice instructions to selected text
- Reformulation: Clean up and lightly reformat transcribed text
- Translation: Translate text to target language
"""

from .config import config

# Lazy import to avoid loading google-genai unless needed
_genai_client = None


def _get_client():
    """Get or create the Gemini client (lazy initialization)."""
    global _genai_client

    if _genai_client is not None:
        return _genai_client

    if not config.GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY not configured. Set it in your environment.")

    try:
        from google import genai

        _genai_client = genai.Client(api_key=config.GEMINI_API_KEY)
        return _genai_client
    except ImportError as e:
        raise ImportError(
            "google-genai not installed. Install with: pip install google-genai\n"
            "Or: pip install dicton[llm]"
        ) from e


def act_on_text(selected_text: str, instruction: str) -> str | None:
    """Apply a voice instruction to selected text using LLM.

    Args:
        selected_text: The text the user has selected.
        instruction: The voice instruction (e.g., "make this more formal").

    Returns:
        The modified text, or None on error.
    """
    if not selected_text or not instruction:
        return None

    prompt = f"""You are a text manipulation assistant. Apply the user's instruction to the provided text.

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

    try:
        client = _get_client()
        response = client.models.generate_content(
            model=config.GEMINI_MODEL,
            contents=prompt,
        )

        if response.text:
            return response.text.strip()
        return None

    except Exception as e:
        if config.DEBUG:
            print(f"LLM error: {e}")
        return None


def reformulate(text: str, language: str | None = None) -> str | None:
    """Lightly reformulate text to clean up grammar and filler words.

    Args:
        text: The transcribed text to reformulate.
        language: Optional language code (e.g., 'en', 'fr') to ensure output matches.

    Returns:
        The reformulated text, or None on error.
    """
    if not text:
        return None

    language_instruction = ""
    if language:
        language_instruction = f"The text is in {language}. Keep your output in the same language."

    prompt = f"""You are a text cleanup assistant. Lightly reformulate the following text.

IMPORTANT RULES:
1. Remove filler words (um, uh, like, you know, etc.)
2. Fix minor grammar issues
3. DO NOT change the meaning or tone
4. DO NOT add or remove content
5. Preserve the speaker's voice and style
6. Return ONLY the cleaned text, no explanations
{language_instruction}

TEXT TO CLEAN:
{text}

CLEANED TEXT:"""

    try:
        client = _get_client()
        response = client.models.generate_content(
            model=config.GEMINI_MODEL,
            contents=prompt,
        )

        if response.text:
            return response.text.strip()
        return None

    except Exception as e:
        if config.DEBUG:
            print(f"LLM reformulation error: {e}")
        return None


def translate(text: str, target_language: str = "English") -> str | None:
    """Translate text to target language.

    Args:
        text: The text to translate.
        target_language: The language to translate to (default: English).

    Returns:
        The translated text, or None on error.
    """
    if not text:
        return None

    prompt = f"""You are a translator. Translate the following text to {target_language}.

IMPORTANT RULES:
1. Provide an accurate, natural translation
2. Preserve the original tone and style
3. Keep formatting (paragraphs, punctuation) consistent
4. Return ONLY the translated text, no explanations

TEXT TO TRANSLATE:
{text}

TRANSLATION:"""

    try:
        client = _get_client()
        response = client.models.generate_content(
            model=config.GEMINI_MODEL,
            contents=prompt,
        )

        if response.text:
            return response.text.strip()
        return None

    except Exception as e:
        if config.DEBUG:
            print(f"LLM translation error: {e}")
        return None


def is_available() -> bool:
    """Check if LLM processing is available (API key configured, library installed)."""
    if not config.GEMINI_API_KEY:
        return False

    try:
        from google import genai  # noqa: F401

        return True
    except ImportError:
        return False
