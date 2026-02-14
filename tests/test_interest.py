"""Tests for interest tracking system."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pytest

from spanish_vibes import db
from spanish_vibes.db import init_db, seed_interest_topics, get_all_interest_topics, _open_connection
from spanish_vibes.interest import CardSignal, InterestTracker, get_topic_id_for_conversation


@pytest.fixture(autouse=True)
def _setup_db(tmp_path):
    db.DB_PATH = tmp_path / "test.db"
    init_db()
    seed_interest_topics()


def _get_topic_id(slug: str) -> int:
    with _open_connection() as conn:
        row = conn.execute("SELECT id FROM interest_topics WHERE slug = ?", (slug,)).fetchone()
    return int(row["id"])


class TestSeedTopics:
    def test_seeds_default_topics(self):
        topics = get_all_interest_topics()
        assert len(topics) >= 20

    def test_football_has_sports_parent(self):
        sports_id = _get_topic_id("sports")
        with _open_connection() as conn:
            row = conn.execute("SELECT parent_id FROM interest_topics WHERE slug = ?", ("football",)).fetchone()
        assert int(row["parent_id"]) == sports_id

    def test_seed_is_idempotent(self):
        count1 = len(get_all_interest_topics())
        seed_interest_topics()
        count2 = len(get_all_interest_topics())
        assert count1 == count2


class TestScoreIncreasesOnCorrectHighDwell:
    """Score should increase when the user gets a card correct with high dwell time."""

    def test_correct_high_dwell_increases_score(self):
        tracker = InterestTracker()
        topic_id = _get_topic_id("sports")

        signal = CardSignal(
            topic_id=topic_id,
            was_correct=True,
            dwell_time_ms=45_000,  # 45s — well-engaged
            card_type="mcq",
        )
        score = tracker.update_from_card_signal(signal)
        assert score > 0.0, "Score should increase after correct + high dwell"

    def test_multiple_correct_signals_build_score(self):
        tracker = InterestTracker()
        topic_id = _get_topic_id("music")

        # Send several engagement signals
        for _ in range(5):
            tracker.update_from_card_signal(CardSignal(
                topic_id=topic_id,
                was_correct=True,
                dwell_time_ms=40_000,
                card_type="mcq",
            ))

        final_score = tracker.get_decayed_score(topic_id)
        # After 5 correct high-dwell signals, score should be substantial
        assert final_score > 0.5, f"Expected score > 0.5 after 5 good signals, got {final_score}"


class TestStruggleDoesNotBoostScore:
    """Long dwell + wrong answer = struggling, should NOT boost interest score."""

    def test_wrong_high_dwell_does_not_increase(self):
        tracker = InterestTracker()
        topic_id = _get_topic_id("technology")

        # First, ensure there's a baseline score of 0
        initial_score = tracker.get_decayed_score(topic_id)
        assert initial_score == 0.0

        # Struggle signal: long dwell + wrong
        signal = CardSignal(
            topic_id=topic_id,
            was_correct=False,
            dwell_time_ms=30_000,  # >= STRUGGLE_DWELL_THRESHOLD_MS (20s)
            card_type="mcq",
        )
        score = tracker.update_from_card_signal(signal)
        assert score == 0.0, "Struggle (wrong + long dwell) should not boost score"

    def test_struggle_does_not_boost_existing_score(self):
        tracker = InterestTracker()
        topic_id = _get_topic_id("travel")

        # Build up some interest first
        for _ in range(3):
            tracker.update_from_card_signal(CardSignal(
                topic_id=topic_id,
                was_correct=True,
                dwell_time_ms=35_000,
                card_type="mcq",
            ))

        score_before = tracker.get_decayed_score(topic_id)
        assert score_before > 0

        # Now struggle — should not increase
        tracker.update_from_card_signal(CardSignal(
            topic_id=topic_id,
            was_correct=False,
            dwell_time_ms=25_000,
            card_type="mcq",
        ))

        score_after = tracker.get_decayed_score(topic_id)
        assert score_after <= score_before, "Struggle should not boost an existing score"


class TestTimeDecay:
    """Exponential time decay should reduce old scores."""

    def test_decay_reduces_score(self):
        tracker = InterestTracker()
        topic_id = _get_topic_id("food-cooking")

        # Insert a score with a timestamp 30 days ago
        thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
        ts = thirty_days_ago.isoformat(timespec="seconds")
        with _open_connection() as conn:
            conn.execute(
                """
                INSERT INTO user_interest_scores (topic_id, score, last_updated, interaction_count)
                VALUES (?, 0.8, ?, 10)
                """,
                (topic_id, ts),
            )
            conn.commit()

        decayed = tracker.get_decayed_score(topic_id)
        # half_life = 45 days, 30 days elapsed → factor = 0.5^(30/45) ≈ 0.63
        expected_factor = math.pow(0.5, 30.0 / 45.0)
        expected = 0.8 * expected_factor
        assert abs(decayed - expected) < 0.01, f"Expected ~{expected:.3f}, got {decayed:.3f}"
        assert decayed < 0.8, "Decayed score should be less than original"

    def test_no_decay_for_recent_score(self):
        tracker = InterestTracker()
        topic_id = _get_topic_id("gaming")

        # Score just updated
        score = tracker.update_from_card_signal(CardSignal(
            topic_id=topic_id,
            was_correct=True,
            dwell_time_ms=40_000,
            card_type="mcq",
        ))

        decayed = tracker.get_decayed_score(topic_id)
        # Should be virtually identical (within same second)
        assert abs(decayed - score) < 0.01

    def test_very_old_score_decays_near_zero(self):
        tracker = InterestTracker()
        topic_id = _get_topic_id("art")

        # 365 days ago
        old_ts = (datetime.now(timezone.utc) - timedelta(days=365)).isoformat(timespec="seconds")
        with _open_connection() as conn:
            conn.execute(
                "INSERT INTO user_interest_scores (topic_id, score, last_updated, interaction_count) VALUES (?, 0.9, ?, 20)",
                (topic_id, old_ts),
            )
            conn.commit()

        decayed = tracker.get_decayed_score(topic_id)
        # 0.5^(365/45) ≈ 0.003 → 0.9 * 0.003 ≈ 0.003
        assert decayed < 0.01, f"Score should be near zero after a year, got {decayed}"


class TestTopInterests:
    """get_top_interests should return ranked topics."""

    def test_top_interests_ranking(self):
        tracker = InterestTracker()

        # Build different interest levels
        sports_id = _get_topic_id("sports")
        music_id = _get_topic_id("music")
        travel_id = _get_topic_id("travel")

        # Sports: high engagement (10 signals)
        for _ in range(10):
            tracker.update_from_card_signal(CardSignal(
                topic_id=sports_id, was_correct=True, dwell_time_ms=50_000, card_type="mcq",
            ))

        # Music: medium engagement (5 signals)
        for _ in range(5):
            tracker.update_from_card_signal(CardSignal(
                topic_id=music_id, was_correct=True, dwell_time_ms=35_000, card_type="mcq",
            ))

        # Travel: low engagement (2 signals)
        for _ in range(2):
            tracker.update_from_card_signal(CardSignal(
                topic_id=travel_id, was_correct=True, dwell_time_ms=20_000, card_type="mcq",
            ))

        top = tracker.get_top_interests(n=5)
        assert len(top) == 3

        # Sports should be #1 (most + highest dwell)
        assert top[0].topic_id == sports_id
        assert top[0].slug == "sports"

        # Scores should be in descending order
        for i in range(len(top) - 1):
            assert top[i].score >= top[i + 1].score

    def test_empty_when_no_interactions(self):
        tracker = InterestTracker()
        top = tracker.get_top_interests(n=5)
        assert top == []

    def test_limit_respected(self):
        tracker = InterestTracker()

        # Engage with 4 topics
        for slug in ["sports", "music", "travel", "science"]:
            tid = _get_topic_id(slug)
            tracker.update_from_card_signal(CardSignal(
                topic_id=tid, was_correct=True, dwell_time_ms=30_000, card_type="mcq",
            ))

        top = tracker.get_top_interests(n=2)
        assert len(top) == 2


class TestSignalRecording:
    """Card signals should be recorded in the card_signals table."""

    def test_signal_is_recorded(self):
        tracker = InterestTracker()
        topic_id = _get_topic_id("history")

        tracker.update_from_card_signal(CardSignal(
            topic_id=topic_id,
            was_correct=True,
            dwell_time_ms=25_000,
            response_time_ms=3_000,
            card_id=42,
            session_id=1,
            concept_id="greetings",
            card_type="mcq",
        ))

        with _open_connection() as conn:
            row = conn.execute(
                "SELECT * FROM card_signals WHERE topic_id = ?", (topic_id,)
            ).fetchone()

        assert row is not None
        assert int(row["was_correct"]) == 1
        assert int(row["dwell_time_ms"]) == 25_000
        assert int(row["card_id"]) == 42
        assert str(row["card_type"]) == "mcq"


class TestConversationTopicMatching:
    def test_matches_topic_string_to_seeded_topic(self):
        topic_id = get_topic_id_for_conversation("football")
        assert topic_id == _get_topic_id("football")

    def test_matches_broader_topic_phrase(self):
        topic_id = get_topic_id_for_conversation("cooking")
        assert topic_id == _get_topic_id("food-cooking")

    def test_falls_back_to_concept_topic_mapping(self):
        topic_id = get_topic_id_for_conversation("unknown_topic_xyz", concept_id="travel_transport")
        assert topic_id == _get_topic_id("travel")
