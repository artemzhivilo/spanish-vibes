from __future__ import annotations

import os
import tempfile

import pytest

from spanish_vibes.srs import calculate_xp_award, level_from_xp, xp_for_level


# ── XP / Level helpers ──────────────────────────────────────────────


def test_xp_for_level_base_cases() -> None:
    assert xp_for_level(1) == 0
    assert xp_for_level(0) == 0


def test_xp_for_level_progression() -> None:
    assert xp_for_level(2) == 50
    assert xp_for_level(3) == 150
    assert xp_for_level(4) == 300
    assert xp_for_level(5) == 500


def test_level_from_xp_level_1() -> None:
    level, into, needed = level_from_xp(0)
    assert level == 1
    assert into == 0
    assert needed == 50


def test_level_from_xp_mid_level() -> None:
    level, into, needed = level_from_xp(75)
    assert level == 2
    assert into == 25
    assert needed == 100


def test_level_from_xp_exact_boundary() -> None:
    level, into, needed = level_from_xp(50)
    assert level == 2
    assert into == 0
    assert needed == 100


def test_level_from_xp_high() -> None:
    level, into, needed = level_from_xp(500)
    assert level == 5
    assert into == 0


def test_calculate_xp_award_no_streak() -> None:
    assert calculate_xp_award(0) == 10


def test_calculate_xp_award_with_streak() -> None:
    assert calculate_xp_award(1) == 12
    assert calculate_xp_award(5) == 20


def test_calculate_xp_award_streak_capped() -> None:
    assert calculate_xp_award(10) == 30
    assert calculate_xp_award(100) == 30


# ── DB progress functions ────────────────────────────────────────────


@pytest.fixture()
def _tmp_db(monkeypatch: pytest.MonkeyPatch):
    """Use a temporary database for each test."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setattr("spanish_vibes.db.DB_PATH", __import__("pathlib").Path(path))
    from spanish_vibes.db import init_db

    init_db()
    yield path
    os.unlink(path)


def test_get_set_progress(_tmp_db: str) -> None:
    from spanish_vibes.db import get_progress, set_progress

    assert get_progress("foo", "default") == "default"
    set_progress("foo", "42")
    assert get_progress("foo", "default") == "42"


def test_add_xp_accumulates(_tmp_db: str) -> None:
    from spanish_vibes.db import add_xp, get_xp

    assert get_xp() == 0
    result = add_xp(10)
    assert result == 10
    result = add_xp(25)
    assert result == 35
    assert get_xp() == 35


def test_streak_new_user(_tmp_db: str) -> None:
    from spanish_vibes.db import get_streak

    count, last_date = get_streak()
    assert count == 0
    assert last_date == ""


def test_streak_first_practice(_tmp_db: str) -> None:
    from spanish_vibes.db import get_streak, record_practice_today

    result = record_practice_today("2025-01-15")
    assert result == 1
    count, last_date = get_streak()
    assert count == 1
    assert last_date == "2025-01-15"


def test_streak_consecutive_days(_tmp_db: str) -> None:
    from spanish_vibes.db import record_practice_today

    record_practice_today("2025-01-15")
    result = record_practice_today("2025-01-16")
    assert result == 2
    result = record_practice_today("2025-01-17")
    assert result == 3


def test_streak_same_day_idempotent(_tmp_db: str) -> None:
    from spanish_vibes.db import record_practice_today

    record_practice_today("2025-01-15")
    result = record_practice_today("2025-01-15")
    assert result == 1


def test_streak_resets_on_gap(_tmp_db: str) -> None:
    from spanish_vibes.db import record_practice_today

    record_practice_today("2025-01-15")
    record_practice_today("2025-01-16")
    result = record_practice_today("2025-01-18")  # skipped 17th
    assert result == 1


def test_fetch_lesson_mastery_empty(_tmp_db: str) -> None:
    from spanish_vibes.db import fetch_lesson_mastery

    assert fetch_lesson_mastery() == {}
