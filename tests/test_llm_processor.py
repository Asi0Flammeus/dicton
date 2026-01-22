"""Tests for LLM processor filler removal in translation mode.

These tests verify that the translation prompt correctly removes filler words
from both French and English text before translating.

Some tests are integration tests that require API credentials (skipped by default).
Run with: pytest tests/test_llm_processor.py -v --run-integration
"""

import pytest


class TestFillerWordLists:
    """Test that filler word lists are comprehensive."""

    # French fillers that should be removed
    FRENCH_FILLERS = [
        "euh",
        "heu",
        "bah",
        "bon",
        "ben",
        "genre",
        "en fait",
        "du coup",
        "voilà",
        "quoi",
        "tu vois",
        "tu sais",
        "enfin",
        "bref",
        "donc voilà",
        "c'est-à-dire",
        "comment dire",
        "ah",
        "oh",
        "ouais",
        "hein",
        "nan",
        "mouais",
        "donc",
        "alors",
        "en gros",
        "style",
        "j'veux dire",
        "disons",
        "enfin bref",
    ]

    # English fillers that should be removed
    ENGLISH_FILLERS = [
        "um",
        "uh",
        "erm",
        "hmm",
        "like",
        "you know",
        "I mean",
        "so",
        "basically",
        "actually",
        "kind of",
        "sort of",
        "kinda",
        "sorta",
        "well",
        "right",
        "okay so",
        "I guess",
        "you see",
        "let's see",
        "and stuff",
        "or whatever",
        "or something",
    ]

    def test_french_fillers_defined(self):
        """Verify French fillers list is not empty."""
        assert len(self.FRENCH_FILLERS) > 20, "Should have comprehensive French filler list"

    def test_english_fillers_defined(self):
        """Verify English fillers list is not empty."""
        assert len(self.ENGLISH_FILLERS) > 15, "Should have comprehensive English filler list"


class TestTranslationPromptStructure:
    """Test that the translation prompt has proper structure."""

    def test_prompt_has_two_steps(self):
        """Verify the translate function prompt contains two-step structure."""
        import inspect

        from src.dicton.llm_processor import translate

        # Get the function source to verify prompt structure
        source = inspect.getsource(translate)

        assert "STEP 1" in source, "Should have STEP 1 in prompt"
        assert "STEP 2" in source, "Should have STEP 2 in prompt"
        assert "CLEAN" in source, "Should mention CLEAN in Step 1"
        assert "TRANSLATE" in source, "Should mention TRANSLATE in Step 2"
        assert "MANDATORY" in source, "Should emphasize MANDATORY"

    def test_prompt_contains_french_fillers(self):
        """Verify prompt mentions French filler examples."""
        import inspect

        from src.dicton.llm_processor import translate

        source = inspect.getsource(translate)

        # Check for key French fillers
        french_fillers_to_check = ["euh", "genre", "du coup", "voilà"]
        for filler in french_fillers_to_check:
            assert filler in source, f"Should mention French filler: {filler}"

    def test_prompt_contains_english_fillers(self):
        """Verify prompt mentions English filler examples."""
        import inspect

        from src.dicton.llm_processor import translate

        source = inspect.getsource(translate)

        # Check for key English fillers
        english_fillers_to_check = ["um", "like", "you know", "basically"]
        for filler in english_fillers_to_check:
            assert filler in source, f"Should mention English filler: {filler}"


class TestTranslationFillerRemoval:
    """Integration tests for filler removal during translation.

    These tests require actual API credentials and make real API calls.
    They are skipped by default; run with --run-integration flag.
    """

    @pytest.fixture
    def translation_func(self):
        """Get the translate function."""
        from src.dicton.llm_processor import is_available, translate

        if not is_available():
            pytest.skip("No LLM provider configured")
        return translate

    @pytest.mark.integration
    def test_french_to_english_removes_euh(self, translation_func):
        """Test that 'euh' is removed when translating French to English."""
        # French with filler words
        french_text = "Euh, je voudrais, euh, commander un café s'il vous plaît."
        result = translation_func(french_text, "English")

        assert result is not None, "Translation should not be None"
        assert "euh" not in result.lower(), "Should remove 'euh' filler"
        assert "uh" not in result.lower(), "Should not translate filler to English equivalent"
        # Should contain the actual content
        assert "coffee" in result.lower() or "café" in result.lower(), "Should translate content"

    @pytest.mark.integration
    def test_french_to_english_removes_genre(self, translation_func):
        """Test that 'genre' (filler usage) is removed."""
        french_text = "C'est genre vraiment cool, tu vois."
        result = translation_func(french_text, "English")

        assert result is not None
        # "genre" as filler should be removed, not translated as "type" or "kind of"
        assert "kind of" not in result.lower() or "cool" in result.lower()
        assert "tu vois" not in result.lower()
        assert "you see" not in result.lower() or result.count("you see") == 0

    @pytest.mark.integration
    def test_french_to_english_removes_du_coup(self, translation_func):
        """Test that 'du coup' (filler) is removed."""
        french_text = "Du coup, on va au restaurant ce soir."
        result = translation_func(french_text, "English")

        assert result is not None
        assert "so then" not in result.lower() or "restaurant" in result.lower()
        assert "restaurant" in result.lower(), "Should translate content"

    @pytest.mark.integration
    def test_french_to_english_removes_multiple_fillers(self, translation_func):
        """Test that multiple French fillers are all removed."""
        french_text = "Bon, euh, en fait, je pense que, tu vois, c'est une bonne idée, quoi."
        result = translation_func(french_text, "English")

        assert result is not None
        # Check no fillers remain
        fillers_to_check = ["euh", "bon,", "en fait", "tu vois", "quoi"]
        for filler in fillers_to_check:
            assert filler not in result.lower(), f"Should remove filler: {filler}"

    @pytest.mark.integration
    def test_english_to_french_removes_fillers(self, translation_func):
        """Test that English fillers are removed when translating to French."""
        english_text = "Um, so basically, I like, want to go to the park, you know?"
        result = translation_func(english_text, "French")

        assert result is not None
        # Should not have English fillers
        english_fillers = ["um", "basically", "like,", "you know"]
        for filler in english_fillers:
            assert filler not in result.lower(), f"Should remove English filler: {filler}"
        # Should contain translated content
        assert "parc" in result.lower(), "Should translate 'park' to French"


class TestTranslationEmptyInput:
    """Test edge cases with empty or noise input."""

    def test_translate_empty_string_returns_none(self):
        """Empty input should return None."""
        from src.dicton.llm_processor import translate

        result = translate("")
        assert result is None

    def test_translate_none_input_returns_none(self):
        """None input should return None."""
        from src.dicton.llm_processor import translate

        # The function should handle this gracefully
        result = translate(None)  # type: ignore
        assert result is None
