from __future__ import annotations

from spanish_vibes.srs import (
    PERSON_LABELS,
    compare_answers,
    normalize_text,
    person_label,
    strip_accents,
)


def test_strip_accents_removes_diacritics() -> None:
    assert strip_accents("estás") == "estas"
    assert strip_accents("niño") == "nino"
    assert strip_accents("hello") == "hello"


def test_normalize_text_lowercases_and_strips_accents() -> None:
    assert normalize_text("  Estás  Bien  ") == "estas bien"


def test_compare_answers_strict_ignores_accents() -> None:
    assert compare_answers("estás", "estas", "strict") is True
    assert compare_answers("hacen", "hacen", "strict") is True
    assert compare_answers("hacer", "hacr", "strict") is False


def test_compare_answers_lenient_accepts_close_matches() -> None:
    assert compare_answers("hacer", "hacr", "lenient") is True
    assert compare_answers("hola", "xyz", "lenient") is False


def test_person_label_returns_readable_label() -> None:
    assert person_label("1s") == "yo"
    assert person_label("3p") == "ellos/ellas/ustedes"
    assert person_label("unknown") == "unknown"
    assert person_label(None) == ""
    assert person_label("") == ""


def test_person_labels_has_all_standard_codes() -> None:
    expected = {"1s", "2s", "3s", "1p", "2p", "3p"}
    assert set(PERSON_LABELS.keys()) == expected
