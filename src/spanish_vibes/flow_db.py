"""Database operations for Flow Mode sessions, responses, concept knowledge, and MCQ cache."""

from __future__ import annotations

import json
from typing import Any

from .db import _open_connection, now_iso
from .models import ConceptKnowledge, FlowResponse, FlowSession, MCQCard


# ── Session CRUD ──────────────────────────────────────────────────────────────


def create_session(flow_score: float) -> FlowSession:
    """Create a new flow session and return it."""
    timestamp = now_iso()
    with _open_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO flow_sessions (started_at, flow_score, status)
            VALUES (?, ?, 'active')
            """,
            (timestamp, flow_score),
        )
        conn.commit()
        session_id = int(cursor.lastrowid)
    return FlowSession(
        id=session_id,
        started_at=timestamp,
        ended_at=None,
        cards_answered=0,
        correct_count=0,
        flow_score=flow_score,
        xp_earned=0,
        longest_streak=0,
        status="active",
    )


def get_session(session_id: int) -> FlowSession | None:
    with _open_connection() as conn:
        row = conn.execute(
            "SELECT * FROM flow_sessions WHERE id = ?", (session_id,)
        ).fetchone()
    if row is None:
        return None
    return _row_to_session(row)


def update_session(
    session_id: int,
    *,
    cards_answered: int | None = None,
    correct_count: int | None = None,
    flow_score: float | None = None,
    xp_earned: int | None = None,
    longest_streak: int | None = None,
) -> None:
    updates: list[str] = []
    params: list[Any] = []
    if cards_answered is not None:
        updates.append("cards_answered = ?")
        params.append(cards_answered)
    if correct_count is not None:
        updates.append("correct_count = ?")
        params.append(correct_count)
    if flow_score is not None:
        updates.append("flow_score = ?")
        params.append(flow_score)
    if xp_earned is not None:
        updates.append("xp_earned = ?")
        params.append(xp_earned)
    if longest_streak is not None:
        updates.append("longest_streak = ?")
        params.append(longest_streak)
    if not updates:
        return
    params.append(session_id)
    with _open_connection() as conn:
        conn.execute(
            f"UPDATE flow_sessions SET {', '.join(updates)} WHERE id = ?",
            params,
        )
        conn.commit()


def end_session(session_id: int) -> FlowSession | None:
    timestamp = now_iso()
    with _open_connection() as conn:
        conn.execute(
            "UPDATE flow_sessions SET ended_at = ?, status = 'completed' WHERE id = ?",
            (timestamp, session_id),
        )
        conn.commit()
    return get_session(session_id)


def get_active_session() -> FlowSession | None:
    """Return the most recent active session, if any."""
    with _open_connection() as conn:
        row = conn.execute(
            "SELECT * FROM flow_sessions WHERE status = 'active' ORDER BY id DESC LIMIT 1"
        ).fetchone()
    if row is None:
        return None
    return _row_to_session(row)


def get_recent_sessions(limit: int = 10) -> list[FlowSession]:
    """Return the most recent completed sessions."""
    with _open_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM flow_sessions ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [_row_to_session(row) for row in rows]


def _row_to_session(row: Any) -> FlowSession:
    return FlowSession(
        id=int(row["id"]),
        started_at=str(row["started_at"]),
        ended_at=str(row["ended_at"]) if row["ended_at"] else None,
        cards_answered=int(row["cards_answered"]),
        correct_count=int(row["correct_count"]),
        flow_score=float(row["flow_score"]),
        xp_earned=int(row["xp_earned"]),
        longest_streak=int(row["longest_streak"]),
        status=str(row["status"]),
    )


# ── Response recording ────────────────────────────────────────────────────────


def record_response(
    *,
    session_id: int,
    card_id: int | None,
    response_type: str,
    prompt_json: str,
    user_answer: str,
    expected_answer: str,
    is_correct: bool,
    response_time_ms: int | None,
    difficulty_score: float,
    flow_score_after: float,
    concept_id: str | None = None,
    chosen_option: str | None = None,
    misconception_concept: str | None = None,
) -> int:
    timestamp = now_iso()
    with _open_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO flow_responses (
                session_id, card_id, response_type, prompt_json, user_answer,
                expected_answer, is_correct, response_time_ms, difficulty_score,
                flow_score_after, created_at, concept_id, chosen_option, misconception_concept
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id, card_id, response_type, prompt_json, user_answer,
                expected_answer, int(is_correct), response_time_ms, difficulty_score,
                flow_score_after, timestamp, concept_id, chosen_option, misconception_concept,
            ),
        )
        conn.commit()
        return int(cursor.lastrowid)


def get_session_responses(session_id: int) -> list[FlowResponse]:
    with _open_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM flow_responses WHERE session_id = ? ORDER BY id",
            (session_id,),
        ).fetchall()
    return [_row_to_response(row) for row in rows]


def _row_to_response(row: Any) -> FlowResponse:
    return FlowResponse(
        id=int(row["id"]),
        session_id=int(row["session_id"]),
        card_id=int(row["card_id"]) if row["card_id"] is not None else None,
        response_type=str(row["response_type"]),
        prompt_json=str(row["prompt_json"]),
        user_answer=str(row["user_answer"]),
        expected_answer=str(row["expected_answer"]),
        is_correct=bool(row["is_correct"]),
        response_time_ms=int(row["response_time_ms"]) if row["response_time_ms"] is not None else None,
        difficulty_score=float(row["difficulty_score"]),
        flow_score_after=float(row["flow_score_after"]),
        created_at=str(row["created_at"]),
    )


# ── Flow state (singleton) ───────────────────────────────────────────────────


def get_or_create_flow_state() -> dict[str, Any]:
    with _open_connection() as conn:
        row = conn.execute("SELECT * FROM flow_state WHERE id = 1").fetchone()
        if row:
            return dict(row)
        timestamp = now_iso()
        conn.execute(
            """
            INSERT INTO flow_state (id, current_flow_score, total_sessions, total_cards, updated_at)
            VALUES (1, 1000.0, 0, 0, ?)
            """,
            (timestamp,),
        )
        conn.commit()
        return {
            "id": 1,
            "current_flow_score": 1000.0,
            "total_sessions": 0,
            "total_cards": 0,
            "updated_at": timestamp,
        }


def update_flow_state(
    *,
    current_flow_score: float | None = None,
    total_sessions_increment: int = 0,
    total_cards_increment: int = 0,
) -> None:
    state = get_or_create_flow_state()
    new_score = current_flow_score if current_flow_score is not None else state["current_flow_score"]
    new_sessions = int(state["total_sessions"]) + total_sessions_increment
    new_cards = int(state["total_cards"]) + total_cards_increment
    timestamp = now_iso()
    with _open_connection() as conn:
        conn.execute(
            """
            UPDATE flow_state
            SET current_flow_score = ?, total_sessions = ?, total_cards = ?, updated_at = ?
            WHERE id = 1
            """,
            (new_score, new_sessions, new_cards, timestamp),
        )
        conn.commit()


# ── Skill profile ────────────────────────────────────────────────────────────


def update_skill_profile(
    lesson_id: int,
    card_kind: str,
    is_correct: bool,
    response_time_ms: int | None = None,
) -> None:
    timestamp = now_iso()
    with _open_connection() as conn:
        row = conn.execute(
            "SELECT * FROM flow_skill_profile WHERE lesson_id = ? AND card_kind = ?",
            (lesson_id, card_kind),
        ).fetchone()
        if row:
            total = int(row["total_attempts"]) + 1
            correct = int(row["correct_attempts"]) + (1 if is_correct else 0)
            proficiency = correct / total if total > 0 else 0.0
            avg_ms = row["avg_response_ms"]
            if response_time_ms is not None:
                if avg_ms is not None:
                    avg_ms = int((int(avg_ms) * (total - 1) + response_time_ms) / total)
                else:
                    avg_ms = response_time_ms
            conn.execute(
                """
                UPDATE flow_skill_profile
                SET proficiency = ?, total_attempts = ?, correct_attempts = ?,
                    avg_response_ms = ?, last_seen_at = ?
                WHERE lesson_id = ? AND card_kind = ?
                """,
                (proficiency, total, correct, avg_ms, timestamp, lesson_id, card_kind),
            )
        else:
            proficiency = 1.0 if is_correct else 0.0
            conn.execute(
                """
                INSERT INTO flow_skill_profile
                    (lesson_id, card_kind, proficiency, total_attempts, correct_attempts, avg_response_ms, last_seen_at)
                VALUES (?, ?, ?, 1, ?, ?, ?)
                """,
                (lesson_id, card_kind, proficiency, 1 if is_correct else 0, response_time_ms, timestamp),
            )
        conn.commit()


def get_weak_lessons(limit: int = 10) -> list[dict[str, Any]]:
    """Return lessons with lowest proficiency, useful for targeting weak areas."""
    with _open_connection() as conn:
        rows = conn.execute(
            """
            SELECT lesson_id, card_kind, proficiency, total_attempts
            FROM flow_skill_profile
            WHERE total_attempts >= 2
            ORDER BY proficiency ASC, total_attempts DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


# ── AI card cache (legacy, kept for compatibility) ───────────────────────────


def save_ai_card(
    *,
    card_type: str,
    base_card_id: int | None,
    difficulty_score: float,
    prompt: str,
    solution: str,
    extra_json: str = "{}",
    content_hash: str,
) -> int:
    timestamp = now_iso()
    with _open_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM flow_ai_cards WHERE content_hash = ?", (content_hash,)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE flow_ai_cards SET times_used = times_used + 1 WHERE id = ?",
                (int(existing["id"]),),
            )
            conn.commit()
            return int(existing["id"])
        cursor = conn.execute(
            """
            INSERT INTO flow_ai_cards
                (card_type, base_card_id, difficulty_score, prompt, solution, extra_json, content_hash, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (card_type, base_card_id, difficulty_score, prompt, solution, extra_json, content_hash, timestamp),
        )
        conn.commit()
        return int(cursor.lastrowid)


def get_cached_ai_card(content_hash: str) -> dict[str, Any] | None:
    with _open_connection() as conn:
        row = conn.execute(
            "SELECT * FROM flow_ai_cards WHERE content_hash = ?", (content_hash,)
        ).fetchone()
    return dict(row) if row else None


# ── Conversations (legacy, kept for compatibility) ───────────────────────────


def create_conversation(session_id: int, topic: str) -> int:
    timestamp = now_iso()
    with _open_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO flow_conversations (session_id, topic, messages_json, turn_count, completed, created_at)
            VALUES (?, ?, '[]', 0, 0, ?)
            """,
            (session_id, topic, timestamp),
        )
        conn.commit()
        return int(cursor.lastrowid)


def add_conversation_turn(conversation_id: int, role: str, content: str) -> dict[str, Any]:
    with _open_connection() as conn:
        row = conn.execute(
            "SELECT messages_json, turn_count FROM flow_conversations WHERE id = ?",
            (conversation_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"Conversation {conversation_id} not found")
        messages = json.loads(row["messages_json"])
        messages.append({"role": role, "content": content})
        turn_count = int(row["turn_count"]) + (1 if role == "user" else 0)
        conn.execute(
            """
            UPDATE flow_conversations
            SET messages_json = ?, turn_count = ?
            WHERE id = ?
            """,
            (json.dumps(messages), turn_count, conversation_id),
        )
        conn.commit()
    return {"messages": messages, "turn_count": turn_count}


def complete_conversation(conversation_id: int) -> None:
    with _open_connection() as conn:
        conn.execute(
            "UPDATE flow_conversations SET completed = 1 WHERE id = ?",
            (conversation_id,),
        )
        conn.commit()


def get_conversation(conversation_id: int) -> dict[str, Any] | None:
    with _open_connection() as conn:
        row = conn.execute(
            "SELECT * FROM flow_conversations WHERE id = ?", (conversation_id,)
        ).fetchone()
    if row is None:
        return None
    result = dict(row)
    result["messages"] = json.loads(result["messages_json"])
    return result


def get_recent_card_ids(session_id: int, limit: int = 10) -> list[int]:
    """Return the last N card_ids answered in a session (for exclusion)."""
    with _open_connection() as conn:
        rows = conn.execute(
            """
            SELECT card_id FROM flow_responses
            WHERE session_id = ? AND card_id IS NOT NULL
            ORDER BY id DESC LIMIT ?
            """,
            (session_id, limit),
        ).fetchall()
    return [int(row["card_id"]) for row in rows]


# ── Concept Knowledge CRUD ──────────────────────────────────────────────────


def get_all_concept_knowledge() -> dict[str, ConceptKnowledge]:
    """Return all concept knowledge entries as dict keyed by concept_id."""
    with _open_connection() as conn:
        rows = conn.execute("SELECT * FROM concept_knowledge").fetchall()
    return {str(row["concept_id"]): _row_to_knowledge(row) for row in rows}


def get_concept_knowledge(concept_id: str) -> ConceptKnowledge | None:
    with _open_connection() as conn:
        row = conn.execute(
            "SELECT * FROM concept_knowledge WHERE concept_id = ?",
            (concept_id,),
        ).fetchone()
    if row is None:
        return None
    return _row_to_knowledge(row)


def update_concept_knowledge(
    concept_id: str,
    p_mastery: float,
    is_correct: bool,
) -> None:
    """Update concept knowledge: set p_mastery, increment attempts/correct/wrong."""
    timestamp = now_iso()
    with _open_connection() as conn:
        if is_correct:
            conn.execute(
                """
                UPDATE concept_knowledge
                SET p_mastery = ?, n_attempts = n_attempts + 1, n_correct = n_correct + 1,
                    last_seen_at = ?, updated_at = ?
                WHERE concept_id = ?
                """,
                (p_mastery, timestamp, timestamp, concept_id),
            )
        else:
            conn.execute(
                """
                UPDATE concept_knowledge
                SET p_mastery = ?, n_attempts = n_attempts + 1, n_wrong = n_wrong + 1,
                    last_seen_at = ?, updated_at = ?
                WHERE concept_id = ?
                """,
                (p_mastery, timestamp, timestamp, concept_id),
            )
        conn.commit()


def mark_teach_shown(concept_id: str) -> None:
    """Mark that the teach card for a concept has been displayed."""
    timestamp = now_iso()
    with _open_connection() as conn:
        conn.execute(
            "UPDATE concept_knowledge SET teach_shown = 1, updated_at = ? WHERE concept_id = ?",
            (timestamp, concept_id),
        )
        conn.commit()


def _row_to_knowledge(row: Any) -> ConceptKnowledge:
    return ConceptKnowledge(
        concept_id=str(row["concept_id"]),
        p_mastery=float(row["p_mastery"]),
        n_attempts=int(row["n_attempts"]),
        n_correct=int(row["n_correct"]),
        n_wrong=int(row["n_wrong"]),
        teach_shown=bool(row["teach_shown"]),
        last_seen_at=str(row["last_seen_at"]) if row["last_seen_at"] else None,
        updated_at=str(row["updated_at"]),
    )


# ── MCQ Cache ────────────────────────────────────────────────────────────────


def get_cached_mcqs(
    concept_id: str,
    limit: int = 10,
    exclude_ids: list[int] | None = None,
) -> list[MCQCard]:
    """Return cached MCQ cards for a concept."""
    exclude_clause = ""
    params: list[Any] = [concept_id]
    if exclude_ids:
        placeholders = ",".join("?" for _ in exclude_ids)
        exclude_clause = f"AND id NOT IN ({placeholders})"
        params.extend(exclude_ids)
    params.append(limit)

    with _open_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT * FROM flow_mcq_cache
            WHERE concept_id = ? {exclude_clause}
            ORDER BY times_used ASC, RANDOM()
            LIMIT ?
            """,
            params,
        ).fetchall()
    return [_row_to_mcq(row) for row in rows]


def save_mcq_batch(concept_id: str, cards: list[dict[str, Any]]) -> list[int]:
    """Save a batch of MCQ cards. Returns list of inserted IDs."""
    timestamp = now_iso()
    inserted: list[int] = []
    with _open_connection() as conn:
        for card in cards:
            existing = conn.execute(
                "SELECT id FROM flow_mcq_cache WHERE content_hash = ?",
                (card["content_hash"],),
            ).fetchone()
            if existing:
                inserted.append(int(existing["id"]))
                continue

            cursor = conn.execute(
                """
                INSERT INTO flow_mcq_cache
                    (concept_id, question, correct_answer, distractors_json, difficulty, source, content_hash, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    concept_id,
                    card["question"],
                    card["correct_answer"],
                    json.dumps(card["distractors"]),
                    card.get("difficulty", 1),
                    card.get("source", "ai"),
                    card["content_hash"],
                    timestamp,
                ),
            )
            inserted.append(int(cursor.lastrowid))
        conn.commit()
    return inserted


def increment_mcq_usage(mcq_id: int) -> None:
    """Increment the times_used counter for an MCQ card."""
    with _open_connection() as conn:
        conn.execute(
            "UPDATE flow_mcq_cache SET times_used = times_used + 1 WHERE id = ?",
            (mcq_id,),
        )
        conn.commit()


def count_cached_mcqs(concept_id: str) -> int:
    """Return the number of cached MCQ cards for a concept."""
    with _open_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM flow_mcq_cache WHERE concept_id = ?",
            (concept_id,),
        ).fetchone()
    return int(row[0])


def _row_to_mcq(row: Any) -> MCQCard:
    distractors_raw = row["distractors_json"]
    try:
        distractors = json.loads(distractors_raw)
    except (json.JSONDecodeError, TypeError):
        distractors = []
    return MCQCard(
        id=int(row["id"]),
        concept_id=str(row["concept_id"]),
        question=str(row["question"]),
        correct_answer=str(row["correct_answer"]),
        distractors=distractors,
        difficulty=int(row["difficulty"]),
        times_used=int(row["times_used"]),
        content_hash=str(row["content_hash"]),
        source=str(row["source"]),
    )
