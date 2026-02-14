"""Tests for signal collection wiring in flow routes."""

from __future__ import annotations

import pytest

from spanish_vibes import db
from spanish_vibes.db import init_db, seed_interest_topics, _open_connection
from spanish_vibes.interest import CardSignal, InterestTracker


@pytest.fixture(autouse=True)
def _setup_db(tmp_path):
    db.DB_PATH = tmp_path / "test.db"
    init_db()
    seed_interest_topics()


def _get_topic_id(slug: str) -> int:
    with _open_connection() as conn:
        row = conn.execute("SELECT id FROM interest_topics WHERE slug = ?", (slug,)).fetchone()
    return int(row["id"])


class TestSignalWithNoneTopic:
    """Signals with topic_id=None should still be recorded."""

    def test_signal_recorded_with_none_topic(self):
        tracker = InterestTracker()
        signal = CardSignal(
            topic_id=None,
            was_correct=True,
            dwell_time_ms=5_000,
            response_time_ms=3_000,
            card_id=10,
            session_id=1,
            concept_id="greetings",
            card_type="mcq",
        )
        score = tracker.update_from_card_signal(signal)
        assert score == 0.0  # No topic → score is 0

        # Signal should still be in the table
        with _open_connection() as conn:
            row = conn.execute(
                "SELECT * FROM card_signals WHERE card_id = ?", (10,)
            ).fetchone()
        assert row is not None
        assert row["topic_id"] is None
        assert int(row["was_correct"]) == 1
        assert str(row["concept_id"]) == "greetings"

    def test_signal_recorded_with_valid_topic(self):
        tracker = InterestTracker()
        topic_id = _get_topic_id("sports")
        signal = CardSignal(
            topic_id=topic_id,
            was_correct=True,
            dwell_time_ms=30_000,
            response_time_ms=5_000,
            card_id=20,
            session_id=2,
            concept_id="present_tense",
            card_type="mcq",
        )
        score = tracker.update_from_card_signal(signal)
        assert score > 0.0

        with _open_connection() as conn:
            row = conn.execute(
                "SELECT * FROM card_signals WHERE card_id = ?", (20,)
            ).fetchone()
        assert row is not None
        assert int(row["topic_id"]) == topic_id

    def test_multiple_signals_without_topic(self):
        tracker = InterestTracker()
        for i in range(5):
            signal = CardSignal(
                topic_id=None,
                was_correct=i % 2 == 0,
                dwell_time_ms=10_000,
                card_id=100 + i,
                session_id=1,
                card_type="mcq",
            )
            tracker.update_from_card_signal(signal)

        with _open_connection() as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM card_signals WHERE session_id = 1"
            ).fetchone()[0]
        assert count == 5
