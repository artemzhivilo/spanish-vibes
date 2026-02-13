from __future__ import annotations

import difflib
import unicodedata
from typing import Literal

SRS_FAST = True

GradingStrategy = Literal["strict", "lenient"]

PERSON_LABELS: dict[str, str] = {
    "1s": "yo",
    "2s": "tú",
    "3s": "él/ella/usted",
    "1p": "nosotros/as",
    "2p": "vosotros/as",
    "3p": "ellos/ellas/ustedes",
}


def strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value)
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")


def normalize_text(value: str) -> str:
    stripped = strip_accents(value.lower())
    return " ".join(stripped.split())


def compare_answers(expected: str, provided: str, strategy: GradingStrategy) -> bool:
    normalized_expected = normalize_text(expected)
    normalized_provided = normalize_text(provided)
    if strategy == "strict":
        return normalized_expected == normalized_provided
    ratio = difflib.SequenceMatcher(None, normalized_expected, normalized_provided).ratio()
    return ratio >= 0.85


def person_label(code: str | None) -> str:
    if not code:
        return ""
    return PERSON_LABELS.get(code, code)


def xp_for_level(level: int) -> int:
    """Cumulative XP required to reach a given level."""
    if level <= 1:
        return 0
    return sum(50 * n for n in range(1, level))


def level_from_xp(xp: int) -> tuple[int, int, int]:
    """Return (level, xp_into_level, xp_needed_for_next)."""
    level = 1
    while True:
        next_threshold = xp_for_level(level + 1)
        if xp < next_threshold:
            current_threshold = xp_for_level(level)
            xp_into = xp - current_threshold
            xp_needed = next_threshold - current_threshold
            return level, xp_into, xp_needed
        level += 1


def calculate_xp_award(session_streak: int) -> int:
    """XP per correct answer: base 10 + streak bonus (capped at 20)."""
    return 10 + min(session_streak * 2, 20)


__all__ = [
    "GradingStrategy",
    "PERSON_LABELS",
    "SRS_FAST",
    "calculate_xp_award",
    "compare_answers",
    "level_from_xp",
    "normalize_text",
    "person_label",
    "strip_accents",
    "xp_for_level",
]
