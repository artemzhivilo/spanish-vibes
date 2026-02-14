"""Interest tracking system — learns what topics a user enjoys."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .db import _open_connection, get_all_interest_topics, now_iso

# ── Signal weights ────────────────────────────────────────────────────────────

W_CORRECTNESS = 0.40
W_DWELL = 0.30
W_RETURN_FREQUENCY = 0.15
W_PROGRESSION = 0.10
W_CONTINUATION = 0.05

# Dwell time normalization: 30s is "expected", cap at 120s
EXPECTED_DWELL_MS = 30_000
MAX_DWELL_MS = 120_000

# Minimum dwell to count as meaningful engagement (2 seconds)
MIN_DWELL_MS = 2_000

# Struggle detection: long dwell + wrong answer
STRUGGLE_DWELL_THRESHOLD_MS = 20_000

CONCEPT_TOPIC_MAP: dict[str, str] = {
    "food_vocab": "food-cooking",
    "ordering_food": "food-cooking",
    "animals_vocab": "nature-animals",
    "clothing_vocab": "fashion",
    "body_parts": "health",
    "professions": "business",
    "family_vocab": "relationships",
    "hobbies_free_time": "gaming",
    "weather_seasons": "nature-animals",
    "places_in_town": "travel",
    "travel_transport": "travel",
    "shopping": "fashion",
    "health_doctor": "health",
    "my_city": "travel",
    "describing_people": "relationships",
}


def get_topic_id_for_conversation(topic: str, concept_id: str | None = None) -> int | None:
    """Match conversation topic/concept to an interest topic id."""
    topics = get_all_interest_topics()
    if not topics:
        return None

    needle = (topic or "").strip().lower()
    best_match_id: int | None = None
    best_score = -1

    if needle:
        for row in topics:
            topic_id = int(row["id"])
            name = str(row.get("name") or "").strip().lower()
            slug = str(row.get("slug") or "").strip().lower()
            score = -1
            if needle == slug or needle == name:
                score = 5
            elif needle in slug or needle in name:
                score = 3
            elif slug in needle or name in needle:
                score = 2
            if score > best_score:
                best_score = score
                best_match_id = topic_id

    if best_match_id is not None and best_score >= 0:
        return best_match_id

    mapped_slug = CONCEPT_TOPIC_MAP.get((concept_id or "").strip().lower())
    if not mapped_slug:
        return None
    for row in topics:
        if str(row.get("slug") or "").strip().lower() == mapped_slug:
            return int(row["id"])
    return None


@dataclass(slots=True)
class CardSignal:
    """A single card interaction signal."""

    was_correct: bool
    topic_id: int | None = None
    dwell_time_ms: int | None = None
    response_time_ms: int | None = None
    was_skipped: bool = False
    card_id: int | None = None
    session_id: int | None = None
    concept_id: str | None = None
    card_type: str = "mcq"


@dataclass(slots=True)
class TopicScore:
    """A ranked topic with its interest score."""

    topic_id: int
    name: str
    slug: str
    score: float
    interaction_count: int


class InterestTracker:
    """Tracks and updates user interest scores based on card interaction signals."""

    def update_from_card_signal(self, signal: CardSignal) -> float:
        """Process a card signal and update the topic's interest score.

        Returns the new score for the topic (0.0 if no topic).
        """
        # Record the raw signal (even without topic)
        self._record_signal(signal)

        # If no topic assigned, just record and return
        if signal.topic_id is None:
            return 0.0

        # Detect struggle: long dwell + wrong = don't boost interest
        dwell = signal.dwell_time_ms or 0
        if self._is_struggling(signal):
            # Still record the interaction but don't boost score
            self._increment_interaction(signal.topic_id)
            return self._get_score(signal.topic_id)

        # Skip signals with no meaningful engagement
        if signal.was_skipped or dwell < MIN_DWELL_MS:
            self._increment_interaction(signal.topic_id)
            return self._get_score(signal.topic_id)

        # Compute engagement signal
        engagement = self._compute_engagement(signal)

        # Update score with blended approach
        current = self._get_current_record(signal.topic_id)
        old_score = current["score"] if current else 0.0
        interaction_count = (current["interaction_count"] if current else 0) + 1

        # Exponential moving average: more interactions = more stable
        alpha = max(0.05, 1.0 / interaction_count)
        new_score = old_score + alpha * (engagement - old_score)
        new_score = max(0.0, min(1.0, new_score))

        self._upsert_score(signal.topic_id, new_score, interaction_count)
        return new_score

    def get_top_interests(self, n: int = 5) -> list[TopicScore]:
        """Return the top N topics by decayed interest score."""
        now = datetime.now(timezone.utc)

        with _open_connection() as conn:
            rows = conn.execute(
                """
                SELECT s.topic_id, s.score, s.last_updated,
                       s.interaction_count, s.decay_half_life_days,
                       t.name, t.slug
                FROM user_interest_scores s
                JOIN interest_topics t ON t.id = s.topic_id
                WHERE s.interaction_count > 0
                ORDER BY s.score DESC
                """,
            ).fetchall()

        scored: list[TopicScore] = []
        for row in rows:
            decayed = self._apply_decay(
                score=float(row["score"]),
                last_updated=str(row["last_updated"]),
                half_life_days=float(row["decay_half_life_days"]),
                now=now,
            )
            if decayed > 0.001:
                scored.append(TopicScore(
                    topic_id=int(row["topic_id"]),
                    name=str(row["name"]),
                    slug=str(row["slug"]),
                    score=decayed,
                    interaction_count=int(row["interaction_count"]),
                ))

        scored.sort(key=lambda t: t.score, reverse=True)
        return scored[:n]

    def get_decayed_score(self, topic_id: int) -> float:
        """Return the current decayed score for a topic."""
        now = datetime.now(timezone.utc)
        with _open_connection() as conn:
            row = conn.execute(
                "SELECT score, last_updated, decay_half_life_days FROM user_interest_scores WHERE topic_id = ?",
                (topic_id,),
            ).fetchone()
        if row is None:
            return 0.0
        return self._apply_decay(
            score=float(row["score"]),
            last_updated=str(row["last_updated"]),
            half_life_days=float(row["decay_half_life_days"]),
            now=now,
        )

    # ── Internal helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _is_struggling(signal: CardSignal) -> bool:
        """Long dwell + wrong answer = struggling, not interested."""
        dwell = signal.dwell_time_ms or 0
        return not signal.was_correct and dwell >= STRUGGLE_DWELL_THRESHOLD_MS

    @staticmethod
    def _compute_engagement(signal: CardSignal) -> float:
        """Compute the composite engagement signal in [0, 1]."""
        # Correctness: 1.0 if correct, 0.0 if wrong
        correctness = 1.0 if signal.was_correct else 0.0

        # Normalized dwell: how long relative to expected, capped at 1.0
        dwell = signal.dwell_time_ms or 0
        clamped_dwell = max(0, min(dwell, MAX_DWELL_MS))
        normalized_dwell = clamped_dwell / MAX_DWELL_MS

        # Return frequency and progression are session-level metrics
        # that require historical context — use moderate defaults for now
        # and let the EMA handle convergence over time
        return_frequency = 0.5
        progression = 0.5
        continuation = 1.0 if not signal.was_skipped else 0.0

        return (
            W_CORRECTNESS * correctness
            + W_DWELL * normalized_dwell
            + W_RETURN_FREQUENCY * return_frequency
            + W_PROGRESSION * progression
            + W_CONTINUATION * continuation
        )

    @staticmethod
    def _apply_decay(
        score: float,
        last_updated: str,
        half_life_days: float,
        now: datetime,
    ) -> float:
        """Apply exponential time decay: score * 0.5^(days / half_life)."""
        try:
            last_dt = datetime.fromisoformat(last_updated)
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            return score

        days_elapsed = (now - last_dt).total_seconds() / 86400.0
        if days_elapsed <= 0:
            return score

        decay_factor = math.pow(0.5, days_elapsed / half_life_days)
        return score * decay_factor

    @staticmethod
    def _get_score(topic_id: int) -> float:
        with _open_connection() as conn:
            row = conn.execute(
                "SELECT score FROM user_interest_scores WHERE topic_id = ?",
                (topic_id,),
            ).fetchone()
        return float(row["score"]) if row else 0.0

    @staticmethod
    def _get_current_record(topic_id: int) -> dict[str, Any] | None:
        with _open_connection() as conn:
            row = conn.execute(
                "SELECT * FROM user_interest_scores WHERE topic_id = ?",
                (topic_id,),
            ).fetchone()
        return dict(row) if row else None

    @staticmethod
    def _upsert_score(topic_id: int, score: float, interaction_count: int) -> None:
        timestamp = now_iso()
        with _open_connection() as conn:
            conn.execute(
                """
                INSERT INTO user_interest_scores (topic_id, score, last_updated, interaction_count)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(topic_id) DO UPDATE SET
                    score = excluded.score,
                    last_updated = excluded.last_updated,
                    interaction_count = excluded.interaction_count
                """,
                (topic_id, score, timestamp, interaction_count),
            )
            conn.commit()

    @staticmethod
    def _increment_interaction(topic_id: int) -> None:
        timestamp = now_iso()
        with _open_connection() as conn:
            existing = conn.execute(
                "SELECT topic_id FROM user_interest_scores WHERE topic_id = ?",
                (topic_id,),
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE user_interest_scores SET interaction_count = interaction_count + 1, last_updated = ? WHERE topic_id = ?",
                    (timestamp, topic_id),
                )
            else:
                conn.execute(
                    "INSERT INTO user_interest_scores (topic_id, score, last_updated, interaction_count) VALUES (?, 0.0, ?, 1)",
                    (topic_id, timestamp),
                )
            conn.commit()

    @staticmethod
    def _record_signal(signal: CardSignal) -> None:
        timestamp = now_iso()
        with _open_connection() as conn:
            conn.execute(
                """
                INSERT INTO card_signals
                    (card_id, session_id, dwell_time_ms, was_correct, response_time_ms,
                     was_skipped, topic_id, concept_id, card_type, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    signal.card_id,
                    signal.session_id,
                    signal.dwell_time_ms,
                    int(signal.was_correct),
                    signal.response_time_ms,
                    int(signal.was_skipped),
                    signal.topic_id,
                    signal.concept_id,
                    signal.card_type,
                    timestamp,
                ),
            )
            conn.commit()


__all__ = [
    "CardSignal",
    "CONCEPT_TOPIC_MAP",
    "InterestTracker",
    "TopicScore",
    "get_topic_id_for_conversation",
]
