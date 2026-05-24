"""Deterministic Whisper-hallucination scrubber."""

from __future__ import annotations

import pytest

from dicton.hallucinations import strip_hallucinations


@pytest.mark.parametrize(
    "raw",
    [
        "Sous-titrage Société Radio-Canada",
        "Sous-titrage de la Société Radio-Canada.",
        "Sous-titres réalisés par la communauté d'Amara.org",
        "Sous-titres réalisés par l’Amara.org.",
        "❤️ par SousTitreur.com",
        "Merci d'avoir regardé cette vidéo.",
        "Abonnez-vous à la chaîne.",
        "N'oubliez pas de vous abonner.",
        "[Musique]",
    ],
)
def test_known_hallucinations_are_stripped(raw: str) -> None:
    assert strip_hallucinations(raw) == ""


def test_hallucination_around_real_text_keeps_content() -> None:
    raw = "Bonjour, je teste la dictée. Sous-titrage Société Radio-Canada."
    out = strip_hallucinations(raw)
    assert "Radio-Canada" not in out
    assert "Bonjour" in out and "dictée" in out


def test_normal_text_is_passthrough() -> None:
    raw = "Je voudrais relire le commit de la pull request avant le meeting."
    assert strip_hallucinations(raw) == raw


def test_empty_input_returns_empty() -> None:
    assert strip_hallucinations("") == ""


def test_collapses_double_spaces_after_removal() -> None:
    raw = "Salut. Sous-titrage Société Radio-Canada. À demain."
    out = strip_hallucinations(raw)
    assert "  " not in out
    assert out.startswith("Salut.")
    assert out.endswith("À demain.")
