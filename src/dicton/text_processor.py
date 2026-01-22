"""Text processing with custom dictionary and filler word removal for Dicton."""

import json
import re
from difflib import SequenceMatcher
from pathlib import Path

# Language-aware filler words
FILLER_WORDS = {
    # English fillers
    "en": {
        "um",
        "uh",
        "uhm",
        "umm",
        "er",
        "err",
        "ah",
        "ahh",
        "eh",
        "hmm",
        "hm",
        "mm",
        "mmm",
        "mhm",
        "uh-huh",
        "uh huh",
        "like",
        "you know",
        "i mean",
        "sort of",
        "kind of",
        "basically",
        "actually",
        "literally",
        "honestly",
        "so",
        "well",
        "right",
        "okay so",
        "yeah so",
    },
    # French fillers
    "fr": {
        "euh",
        "heu",
        "hein",
        "bah",
        "ben",
        "beh",
        "quoi",
        "genre",
        "en fait",
        "du coup",
        "voilà",
        "bon",
        "alors",
        "donc",
        "tu vois",
        "tu sais",
    },
    # German fillers
    "de": {
        "äh",
        "ähm",
        "öh",
        "öhm",
        "hm",
        "hmm",
        "also",
        "halt",
        "quasi",
        "sozusagen",
        "irgendwie",
        "eigentlich",
        "ja",
        "ne",
        "na ja",
    },
    # Spanish fillers
    "es": {
        "eh",
        "em",
        "este",
        "esto",
        "bueno",
        "pues",
        "o sea",
        "es que",
        "tipo",
        "como que",
        "vale",
        "sabes",
        "mira",
        "entonces",
    },
    # Common (language-agnostic)
    "common": {
        "um",
        "uh",
        "uhm",
        "er",
        "ah",
        "hmm",
        "mm",
    },
}


class TextProcessor:
    """Process transcribed text with custom dictionary and filler word removal."""

    # Default similarity threshold (0.0-1.0, higher = stricter matching)
    # 0.65 works well for typical STT misspellings (e.g., "rogzy" → "Roxy")
    DEFAULT_SIMILARITY_THRESHOLD = 0.65

    def __init__(
        self,
        dictionary_path: Path | str | None = None,
        filter_fillers: bool = True,
        language: str = "auto",
        similarity_threshold: float | None = None,
    ):
        """Initialize the text processor.

        Args:
            dictionary_path: Path to custom dictionary JSON file.
                            If None, uses default location (~/.config/dicton/dictionary.json)
            filter_fillers: If True, remove filler words from transcriptions.
            language: Language code for filler detection ('en', 'fr', 'de', 'es', 'auto').
                     'auto' uses common fillers across all languages.
            similarity_threshold: Minimum similarity ratio (0.0-1.0) for fuzzy matching.
                                 If None, uses default (0.75).
        """
        self.dictionary: dict[str, str] = {}
        self.case_sensitive: dict[str, str] = {}  # For exact case matches
        self.patterns: list[tuple[re.Pattern, str]] = []  # For regex patterns
        self.similarity_words: list[str] = []  # Words for fuzzy matching
        self.similarity_threshold = similarity_threshold or self.DEFAULT_SIMILARITY_THRESHOLD
        self.filter_fillers = filter_fillers
        self.language = language

        # Default dictionary location
        if dictionary_path is None:
            self.dictionary_path = Path.home() / ".config" / "dicton" / "dictionary.json"
        else:
            self.dictionary_path = Path(dictionary_path)

        self._load_dictionary()
        self._compile_filler_patterns()

    def _load_dictionary(self) -> None:
        """Load custom dictionary from JSON file."""
        if not self.dictionary_path.exists():
            # Create default dictionary with examples (commented out)
            self._create_default_dictionary()
            return

        try:
            with open(self.dictionary_path, encoding="utf-8") as f:
                data = json.load(f)

            # Load simple word replacements (case-insensitive)
            self.dictionary = {k.lower(): v for k, v in data.get("replacements", {}).items()}

            # Load case-sensitive replacements
            self.case_sensitive = data.get("case_sensitive", {})

            # Load regex patterns
            for pattern_data in data.get("patterns", []):
                try:
                    pattern = re.compile(pattern_data["pattern"], re.IGNORECASE)
                    self.patterns.append((pattern, pattern_data["replacement"]))
                except re.error:
                    pass  # Skip invalid regex patterns

            # Load similarity words (for fuzzy matching)
            self.similarity_words = [
                w
                for w in data.get("similarity_words", [])
                if not w.startswith("_")  # Skip example entries
            ]

        except (json.JSONDecodeError, OSError):
            # If file is corrupted or unreadable, use empty dictionary
            self.dictionary = {}
            self.case_sensitive = {}
            self.patterns = []
            self.similarity_words = []

    def _create_default_dictionary(self) -> None:
        """Create a default dictionary file with examples."""
        default_data = {
            "_comment": "Custom dictionary for Dicton - word corrections",
            "similarity_words": [
                "_ExampleName",
                "_ExampleTerm",
            ],
            "_similarity_comment": "Words above are matched using fuzzy similarity (e.g., 'rogzy' → 'Roxy')",
            "replacements": {
                "_example_typo": "_corrected_word",
            },
            "case_sensitive": {
                "_Example": "_Example_Corrected",
            },
            "patterns": [
                {
                    "_comment": "Example regex pattern (disabled)",
                    "pattern": "_disabled_pattern",
                    "replacement": "_replacement",
                }
            ],
        }

        try:
            self.dictionary_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.dictionary_path, "w", encoding="utf-8") as f:
                json.dump(default_data, f, indent=2, ensure_ascii=False)
        except OSError:
            pass  # Silently fail if we can't create the file

    def reload_dictionary(self) -> None:
        """Reload the dictionary from disk."""
        self.dictionary = {}
        self.case_sensitive = {}
        self.patterns = []
        self.similarity_words = []
        self._load_dictionary()

    def _compile_filler_patterns(self) -> None:
        """Compile regex patterns for filler word removal."""
        self.filler_patterns: list[re.Pattern] = []

        if not self.filter_fillers:
            return

        # Get filler words based on language setting
        fillers: set[str] = set()

        if self.language == "auto":
            # Use common fillers that work across languages
            fillers = FILLER_WORDS.get("common", set()).copy()
        else:
            # Use language-specific fillers
            fillers = FILLER_WORDS.get(self.language, set()).copy()
            # Also include common fillers
            fillers.update(FILLER_WORDS.get("common", set()))

        # Sort by length (longest first) to match multi-word fillers before single words
        sorted_fillers = sorted(fillers, key=len, reverse=True)

        for filler in sorted_fillers:
            # Create pattern that matches filler at word boundaries
            # Also handles fillers at start/end of sentence with optional punctuation
            pattern = re.compile(
                r"(?:^|(?<=\s))" + re.escape(filler) + r"(?:,?\s*|[.!?]?\s*$)",
                re.IGNORECASE,
            )
            self.filler_patterns.append(pattern)

    def set_filler_filtering(self, enabled: bool, language: str | None = None) -> None:
        """Enable or disable filler word filtering.

        Args:
            enabled: If True, filter filler words.
            language: Optional language code to set. If None, keeps current language.
        """
        self.filter_fillers = enabled
        if language is not None:
            self.language = language
        self._compile_filler_patterns()

    def _find_similar_word(self, word: str) -> str | None:
        """Find the most similar word from similarity_words dictionary.

        Args:
            word: The word to find a match for.

        Returns:
            The matching dictionary word if similarity >= threshold, else None.
        """
        if not self.similarity_words or not word:
            return None

        word_lower = word.lower()
        best_match = None
        best_ratio = 0.0

        for dict_word in self.similarity_words:
            ratio = SequenceMatcher(None, word_lower, dict_word.lower()).ratio()
            if ratio > best_ratio and ratio >= self.similarity_threshold:
                best_ratio = ratio
                best_match = dict_word

        return best_match

    def _apply_similarity_corrections(self, text: str) -> str:
        """Apply similarity-based word corrections to text.

        Args:
            text: The text to process.

        Returns:
            Text with similar words replaced by dictionary matches.
        """
        if not self.similarity_words:
            return text

        # Split into words while preserving punctuation positions
        words = re.findall(r"(\w+|\W+)", text)
        result_words = []

        for token in words:
            if re.match(r"\w+", token):  # It's a word
                match = self._find_similar_word(token)
                if match:
                    # Preserve original capitalization style
                    if token.isupper():
                        result_words.append(match.upper())
                    elif token[0].isupper():
                        result_words.append(match[0].upper() + match[1:])
                    else:
                        result_words.append(match.lower())
                else:
                    result_words.append(token)
            else:  # Punctuation/whitespace
                result_words.append(token)

        return "".join(result_words)

    def process(self, text: str) -> str:
        """Process text with filler removal and custom dictionary replacements.

        Args:
            text: The transcribed text to process.

        Returns:
            Processed text with fillers removed and replacements applied.
        """
        if not text:
            return text

        result = text

        # Remove filler words first (before dictionary replacements)
        if self.filter_fillers:
            for pattern in self.filler_patterns:
                result = pattern.sub(" ", result)
            # Clean up multiple spaces and trim
            result = re.sub(r"\s+", " ", result).strip()

        # Apply similarity-based corrections (fuzzy matching)
        result = self._apply_similarity_corrections(result)

        # Apply case-sensitive replacements first (exact matches)
        for original, replacement in self.case_sensitive.items():
            if original.startswith("_"):  # Skip example entries
                continue
            result = result.replace(original, replacement)

        # Apply case-insensitive word replacements
        for original, replacement in self.dictionary.items():
            if original.startswith("_"):  # Skip example entries
                continue
            # Use word boundary matching for whole words only
            pattern = re.compile(r"\b" + re.escape(original) + r"\b", re.IGNORECASE)
            result = pattern.sub(replacement, result)

        # Apply regex patterns
        for pattern, replacement in self.patterns:
            if pattern.pattern.startswith("_"):  # Skip example entries
                continue
            result = pattern.sub(replacement, result)

        return result

    def add_replacement(
        self, original: str, replacement: str, case_sensitive: bool = False
    ) -> None:
        """Add a new replacement to the dictionary.

        Args:
            original: The word/phrase to replace.
            replacement: The replacement text.
            case_sensitive: If True, match exact case. If False, match any case.
        """
        if case_sensitive:
            self.case_sensitive[original] = replacement
        else:
            self.dictionary[original.lower()] = replacement

        self._save_dictionary()

    def remove_replacement(self, original: str) -> bool:
        """Remove a replacement from the dictionary.

        Args:
            original: The word/phrase to remove.

        Returns:
            True if removed, False if not found.
        """
        removed = False

        if original in self.case_sensitive:
            del self.case_sensitive[original]
            removed = True

        if original.lower() in self.dictionary:
            del self.dictionary[original.lower()]
            removed = True

        if removed:
            self._save_dictionary()

        return removed

    def add_similarity_word(self, word: str) -> None:
        """Add a word to the similarity dictionary.

        Args:
            word: The correct spelling of the word to add.
        """
        if word and word not in self.similarity_words:
            self.similarity_words.append(word)
            self._save_dictionary()

    def remove_similarity_word(self, word: str) -> bool:
        """Remove a word from the similarity dictionary.

        Args:
            word: The word to remove.

        Returns:
            True if removed, False if not found.
        """
        if word in self.similarity_words:
            self.similarity_words.remove(word)
            self._save_dictionary()
            return True
        return False

    def get_similarity_words(self) -> list[str]:
        """Get all words in the similarity dictionary.

        Returns:
            List of similarity words.
        """
        return self.similarity_words.copy()

    def _save_dictionary(self) -> None:
        """Save the current dictionary to disk."""
        data = {
            "_comment": "Custom dictionary for Dicton - word corrections",
            "similarity_words": self.similarity_words,
            "replacements": self.dictionary,
            "case_sensitive": self.case_sensitive,
            "patterns": [
                {"pattern": p.pattern, "replacement": r}
                for p, r in self.patterns
                if not p.pattern.startswith("_")
            ],
        }

        try:
            self.dictionary_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.dictionary_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except OSError:
            pass

    def get_dictionary_path(self) -> Path:
        """Get the path to the dictionary file."""
        return self.dictionary_path


# Global text processor instance
_text_processor: TextProcessor | None = None


def get_text_processor() -> TextProcessor:
    """Get the global text processor instance.

    Uses settings from config for filler filtering and language.
    """
    global _text_processor
    if _text_processor is None:
        from .config import config

        _text_processor = TextProcessor(
            filter_fillers=config.FILTER_FILLERS,
            language=config.LANGUAGE,
        )
    return _text_processor


def filter_filler_words(text: str, language: str | None = None) -> str:
    """Filter filler words from text.

    Convenience function for simple filler removal without dictionary processing.

    Args:
        text: The text to filter.
        language: Optional language code. If None, uses config setting.

    Returns:
        Text with filler words removed.
    """
    processor = get_text_processor()
    if language is not None and language != processor.language:
        # Create temporary processor with specific language
        temp_processor = TextProcessor(
            filter_fillers=True,
            language=language,
        )
        return temp_processor.process(text)
    return processor.process(text)
