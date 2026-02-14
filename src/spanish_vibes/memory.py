"""Memory persistence and retrieval for persona/user continuity."""

from __future__ import annotations

import re

from .db import _open_connection, now_iso

_TRIVIAL_FACT_PATTERNS: tuple[str, ...] = (
    "learning spanish",
    "learns spanish",
    "studying spanish",
    "aprendiendo espanol",
    "aprendiendo español",
    "estudia espanol",
    "estudia español",
)


def _clean_text(text: str) -> str:
    return " ".join(text.strip().split())


def _score_importance(memory_text: str) -> float:
    """Score memory importance based on content."""
    text = memory_text.lower()
    if any(
        word in text
        for word in (
            "name",
            "nombre",
            "family",
            "familia",
            "pet",
            "mascota",
            "dog",
            "perro",
            "cat",
            "gato",
            "lives in",
            "vive en",
        )
    ):
        return 0.8
    if any(
        word in text
        for word in (
            "struggled",
            "difficulty",
            "error",
            "mistake",
            "strength",
            "good at",
            "strong",
        )
    ):
        return 0.7
    if any(
        word in text
        for word in (
            "likes",
            "loves",
            "enjoys",
            "interested",
            "favorite",
            "prefers",
        )
    ):
        return 0.6
    return 0.4


def _normalize_fact_key(fact: str) -> str:
    normalized = re.sub(r"[^a-z0-9\s:]", "", fact.lower())
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized[:50]


def _fact_confidence(fact: str) -> float:
    text = fact.lower()
    if any(token in text for token in ("named ", "name is ", " vive en ", " lives in ")):
        return 0.8
    if any(token in text for token in ("likes ", "loves ", "prefers ", "has ")):
        return 0.7
    return 0.6


def _is_trivial_fact(fact: str) -> bool:
    text = fact.lower()
    return any(pattern in text for pattern in _TRIVIAL_FACT_PATTERNS)


def prune_persona_memories(persona_id: str, max_memories: int = 20) -> int:
    """Delete oldest/least-important memories when over the cap."""
    with _open_connection() as conn:
        rows = conn.execute(
            """
            SELECT id
            FROM persona_memories
            WHERE persona_id = ?
            ORDER BY importance_score DESC, created_at DESC, id DESC
            """,
            (persona_id,),
        ).fetchall()
        if len(rows) <= max_memories:
            return 0
        keep_ids = {int(row["id"]) for row in rows[:max_memories]}
        all_ids = [int(row["id"]) for row in rows]
        prune_ids = [memory_id for memory_id in all_ids if memory_id not in keep_ids]
        if not prune_ids:
            return 0
        placeholders = ",".join("?" for _ in prune_ids)
        conn.execute(
            f"DELETE FROM persona_memories WHERE id IN ({placeholders})",
            prune_ids,
        )
        conn.commit()
        return len(prune_ids)


def store_persona_memories(
    persona_id: str,
    observations: list[str],
    conversation_id: int | None = None,
) -> int:
    """Store persona-specific observations from a conversation."""
    cleaned = [_clean_text(obs) for obs in observations if obs and _clean_text(obs)]
    if not cleaned:
        return 0
    timestamp = now_iso()
    inserted = 0
    with _open_connection() as conn:
        for memory_text in cleaned:
            conn.execute(
                """
                INSERT INTO persona_memories (
                    persona_id, memory_text, conversation_id, importance_score, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    persona_id,
                    memory_text,
                    conversation_id,
                    _score_importance(memory_text),
                    timestamp,
                ),
            )
            inserted += 1
        conn.commit()
    prune_persona_memories(persona_id, max_memories=20)
    return inserted


def store_user_facts(
    facts: list[str],
    conversation_id: int | None = None,
) -> int:
    """Store user facts discovered during a conversation."""
    cleaned = [_clean_text(fact) for fact in facts if fact and _clean_text(fact)]
    if not cleaned:
        return 0
    upserts = 0
    timestamp = now_iso()
    with _open_connection() as conn:
        for fact in cleaned:
            if _is_trivial_fact(fact):
                continue
            key = _normalize_fact_key(fact)
            if not key:
                continue
            confidence = _fact_confidence(fact)
            existing = conn.execute(
                "SELECT value, confidence FROM user_profile WHERE key = ?",
                (key,),
            ).fetchone()
            if existing is None:
                conn.execute(
                    """
                    INSERT INTO user_profile (
                        key, value, source_conversation_id, confidence, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (key, fact, conversation_id, confidence, timestamp, timestamp),
                )
                upserts += 1
                continue

            existing_value = str(existing["value"] or "")
            existing_confidence = float(existing["confidence"] or 0.0)
            chosen_value = fact if len(fact) > len(existing_value) else existing_value
            chosen_confidence = max(existing_confidence, confidence)
            conn.execute(
                """
                UPDATE user_profile
                SET value = ?, source_conversation_id = ?, confidence = ?, updated_at = ?
                WHERE key = ?
                """,
                (chosen_value, conversation_id, chosen_confidence, timestamp, key),
            )
            upserts += 1
        conn.commit()
    return upserts


def get_persona_memories(persona_id: str, limit: int = 10) -> list[str]:
    """Get recent memories for a persona, ordered by importance then recency."""
    with _open_connection() as conn:
        rows = conn.execute(
            """
            SELECT memory_text
            FROM persona_memories
            WHERE persona_id = ?
            ORDER BY importance_score DESC, created_at DESC, id DESC
            LIMIT ?
            """,
            (persona_id, limit),
        ).fetchall()
    return [str(row["memory_text"]) for row in rows]


def get_user_profile(limit: int = 10) -> list[str]:
    """Get user profile facts ordered by confidence then recency."""
    with _open_connection() as conn:
        rows = conn.execute(
            """
            SELECT value
            FROM user_profile
            ORDER BY confidence DESC, updated_at DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [str(row["value"]) for row in rows]


__all__ = [
    "get_persona_memories",
    "get_user_profile",
    "prune_persona_memories",
    "store_persona_memories",
    "store_user_facts",
]
