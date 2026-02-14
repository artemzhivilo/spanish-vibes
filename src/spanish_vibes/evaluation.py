"""LLM-powered conversation evaluation for Flow Mode."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .conversation import ConversationMessage
from .db import _open_connection, now_iso

from .flow_ai import ai_available, _get_client
from .personas import load_persona, get_persona_prompt
from .concepts import load_concepts


@dataclass(slots=True)
class ConceptEvidence:
    concept_id: str
    usage_count: int
    correct_count: int
    errors: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ConversationEvaluation:
    concepts_demonstrated: list[ConceptEvidence] = field(default_factory=list)
    vocabulary_used: list[str] = field(default_factory=list)
    user_facts: list[str] = field(default_factory=list)
    persona_observations: list[str] = field(default_factory=list)
    engagement_quality: float = 0.0
    estimated_cefr: dict[str, str] = field(default_factory=dict)
    summary_for_user: str = ""
    concept_required_result: dict[str, Any] = field(default_factory=dict)


def _empty_evaluation() -> ConversationEvaluation:
    return ConversationEvaluation()


def evaluate_conversation(
    messages: list[Any],
    concept_id: str,
    topic: str,
    difficulty: int,
    persona_id: str | None,
    conversation_type: str = "general_chat",
    target_concept_id: str | None = None,
) -> ConversationEvaluation:
    """Call GPT to extract structured evaluation for a conversation."""
    if not ai_available():
        return _empty_evaluation()

    client = _get_client()
    if client is None:
        return _empty_evaluation()

    persona = load_persona(persona_id)
    persona_prompt = get_persona_prompt(persona)

    transcript_lines: list[str] = []
    for msg in messages:
        prefix = "Persona" if msg.role == "ai" else ("System" if msg.role == "system" else "Learner")
        content = msg.content if hasattr(msg, "content") else str(msg)
        transcript_lines.append(f"{prefix}: {content}")
    transcript = "\n".join(transcript_lines)

    system_prompt = (
        "You are an expert Spanish conversation evaluator."
        " Analyze the dialogue and return STRICT JSON describing what the learner"
        " demonstrated. Follow the schema carefully."
    )

    user_prompt = (
        f"Persona: {persona.name}\n"
        f"Persona prompt:\n{persona_prompt}\n---\n"
        f"CONVERSATION TYPE: {conversation_type}\n"
        f"Target concept: {concept_id}\n"
        f"Target concept for diagnostics: {target_concept_id or concept_id}\n"
        f"Topic: {topic}\nDifficulty: {difficulty}\n"
        "Conversation transcript:\n"
        f"{transcript}\n\n"
        "Return JSON with keys: concepts_demonstrated (list with concept_id, usage_count,"
        " correct_count, errors[]), vocabulary_used (array of unique Spanish words),"
        " user_facts (array of natural-language facts learned about the user),"
        " persona_observations (array of observations about engagement),"
        " engagement_quality (0-1 float), estimated_cefr (object mapping categories to"
        " CEFR levels), summary_for_user (short friendly feedback), concept_required_result"
        " (object with target_concept, produced, correct_uses, incorrect_uses when applicable)."
        " Do not include extra text."
    )

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
            max_tokens=800,
            response_format={"type": "json_object"},
        )
        content = (response.choices[0].message.content or "").strip()
        data = json.loads(content)
    except Exception:
        return _empty_evaluation()

    eval_obj = ConversationEvaluation()
    eval_obj.summary_for_user = str(data.get("summary_for_user") or "").strip()
    eval_obj.vocabulary_used = [w.strip() for w in data.get("vocabulary_used", []) if isinstance(w, str)]
    eval_obj.user_facts = [f.strip() for f in data.get("user_facts", []) if isinstance(f, str)]
    eval_obj.persona_observations = [
        f.strip() for f in data.get("persona_observations", []) if isinstance(f, str)
    ]
    eval_obj.engagement_quality = float(data.get("engagement_quality") or 0.0)
    if isinstance(data.get("estimated_cefr"), dict):
        eval_obj.estimated_cefr = {str(k): str(v) for k, v in data["estimated_cefr"].items()}
    if isinstance(data.get("concept_required_result"), dict):
        eval_obj.concept_required_result = {
            str(k): v for k, v in data["concept_required_result"].items()
        }

    concept_entries = data.get("concepts_demonstrated") or []
    for entry in concept_entries:
        concept_id_val = entry.get("concept_id")
        if not concept_id_val:
            continue
        evidence = ConceptEvidence(
            concept_id=str(concept_id_val),
            usage_count=int(entry.get("usage_count") or 0),
            correct_count=int(entry.get("correct_count") or 0),
            errors=[str(e) for e in entry.get("errors", []) if isinstance(e, str)],
        )
        eval_obj.concepts_demonstrated.append(evidence)

    return eval_obj


def compute_enjoyment_score(
    messages: list[ConversationMessage],
    max_turns: int = 4,
    engagement_quality_from_llm: float = 0.5,
) -> float:
    """Compute enjoyment score from behavioral signals (0.0-1.0)."""
    user_messages = [m for m in messages if getattr(m, "role", "") == "user"]
    user_turn_count = len(user_messages)
    word_counts = [len((m.content or "").split()) for m in user_messages]
    avg_words = (sum(word_counts) / user_turn_count) if user_turn_count else 0.0

    if avg_words <= 0:
        message_length_norm = 0.0
    elif avg_words <= 3:
        message_length_norm = 0.2
    elif avg_words <= 7:
        message_length_norm = 0.5
    elif avg_words <= 12:
        message_length_norm = 0.7
    else:
        message_length_norm = 1.0

    safe_max_turns = max(1, max_turns)
    completion_ratio = min(1.0, user_turn_count / safe_max_turns)
    no_early_exit = 1.0 if user_turn_count >= safe_max_turns else 0.0
    response_time_score = 0.5
    engagement_quality = min(1.0, max(0.0, float(engagement_quality_from_llm or 0.0)))

    score = (
        message_length_norm * 0.35
        + completion_ratio * 0.25
        + no_early_exit * 0.20
        + response_time_score * 0.10
        + engagement_quality * 0.10
    )
    return min(1.0, max(0.0, score))


def update_persona_engagement(
    persona_id: str,
    topic_id: int | None,
    enjoyment_score: float,
    avg_message_length: float,
    turn_count: int,
    was_early_exit: bool,
) -> None:
    """Update running engagement metrics for persona+topic and persona-level rows."""
    timestamp = now_iso()
    early_exit_value = 1.0 if was_early_exit else 0.0

    with _open_connection() as conn:
        _upsert_engagement_row(
            conn,
            persona_id=persona_id,
            topic_id=topic_id,
            enjoyment_score=enjoyment_score,
            avg_message_length=avg_message_length,
            turn_count=turn_count,
            early_exit_value=early_exit_value,
            timestamp=timestamp,
        )
        _upsert_engagement_row(
            conn,
            persona_id=persona_id,
            topic_id=None,
            enjoyment_score=enjoyment_score,
            avg_message_length=avg_message_length,
            turn_count=turn_count,
            early_exit_value=early_exit_value,
            timestamp=timestamp,
        )
        conn.commit()


def _upsert_engagement_row(
    conn: Any,
    *,
    persona_id: str,
    topic_id: int | None,
    enjoyment_score: float,
    avg_message_length: float,
    turn_count: int,
    early_exit_value: float,
    timestamp: str,
) -> None:
    if topic_id is None:
        conn.execute(
            """
            INSERT INTO persona_engagement (
                persona_id, topic_id, conversation_count, avg_enjoyment_score,
                avg_message_length, avg_turns, early_exit_rate, last_conversation_at
            )
            VALUES (?, NULL, 1, ?, ?, ?, ?, ?)
            ON CONFLICT(persona_id) WHERE topic_id IS NULL DO UPDATE SET
                conversation_count = persona_engagement.conversation_count + 1,
                avg_enjoyment_score = persona_engagement.avg_enjoyment_score
                    + (? - persona_engagement.avg_enjoyment_score) / (persona_engagement.conversation_count + 1),
                avg_message_length = persona_engagement.avg_message_length
                    + (? - persona_engagement.avg_message_length) / (persona_engagement.conversation_count + 1),
                avg_turns = persona_engagement.avg_turns
                    + (? - persona_engagement.avg_turns) / (persona_engagement.conversation_count + 1),
                early_exit_rate = persona_engagement.early_exit_rate
                    + (? - persona_engagement.early_exit_rate) / (persona_engagement.conversation_count + 1),
                last_conversation_at = excluded.last_conversation_at
            """,
            (
                persona_id,
                enjoyment_score,
                avg_message_length,
                turn_count,
                early_exit_value,
                timestamp,
                enjoyment_score,
                avg_message_length,
                turn_count,
                early_exit_value,
            ),
        )
        return

    conn.execute(
        """
        INSERT INTO persona_engagement (
            persona_id, topic_id, conversation_count, avg_enjoyment_score,
            avg_message_length, avg_turns, early_exit_rate, last_conversation_at
        )
        VALUES (?, ?, 1, ?, ?, ?, ?, ?)
        ON CONFLICT(persona_id, topic_id) DO UPDATE SET
            conversation_count = persona_engagement.conversation_count + 1,
            avg_enjoyment_score = persona_engagement.avg_enjoyment_score
                + (? - persona_engagement.avg_enjoyment_score) / (persona_engagement.conversation_count + 1),
            avg_message_length = persona_engagement.avg_message_length
                + (? - persona_engagement.avg_message_length) / (persona_engagement.conversation_count + 1),
            avg_turns = persona_engagement.avg_turns
                + (? - persona_engagement.avg_turns) / (persona_engagement.conversation_count + 1),
            early_exit_rate = persona_engagement.early_exit_rate
                + (? - persona_engagement.early_exit_rate) / (persona_engagement.conversation_count + 1),
            last_conversation_at = excluded.last_conversation_at
        """,
        (
            persona_id,
            topic_id,
            enjoyment_score,
            avg_message_length,
            turn_count,
            early_exit_value,
            timestamp,
            enjoyment_score,
            avg_message_length,
            turn_count,
            early_exit_value,
        ),
    )


def apply_placement_results(evaluation: ConversationEvaluation) -> dict[str, Any]:
    """Mass-unlock concepts conservatively from placement conversation evidence."""
    concepts = load_concepts()
    cefr = evaluation.estimated_cefr or {}
    grammar_tier = _cefr_to_tier(str(cefr.get("grammar") or "A1"))
    vocab_tier = _cefr_to_tier(str(cefr.get("vocabulary") or "A1"))
    safe_tier = min(grammar_tier, vocab_tier)

    unlocked_count = 0
    timestamp = now_iso()
    with _open_connection() as conn:
        for concept_id, concept in concepts.items():
            if concept.difficulty_level >= safe_tier:
                continue
            row = conn.execute(
                "SELECT p_mastery, n_attempts, n_correct, n_wrong FROM concept_knowledge WHERE concept_id = ?",
                (concept_id,),
            ).fetchone()
            if row is None:
                continue
            p_mastery = max(float(row["p_mastery"] or 0.0), 0.95)
            n_attempts = max(int(row["n_attempts"] or 0), 10)
            n_correct = max(int(row["n_correct"] or 0), 10)
            n_wrong = min(int(row["n_wrong"] or 0), max(0, n_attempts - n_correct))
            conn.execute(
                """
                UPDATE concept_knowledge
                SET p_mastery = ?, n_attempts = ?, n_correct = ?, n_wrong = ?, teach_shown = 1, updated_at = ?
                WHERE concept_id = ?
                """,
                (p_mastery, n_attempts, n_correct, n_wrong, timestamp, concept_id),
            )
            unlocked_count += 1

        demonstrated: list[str] = []
        for evidence in evaluation.concepts_demonstrated:
            if evidence.usage_count <= 0 or evidence.correct_count <= 0:
                continue
            concept_id = evidence.concept_id
            row = conn.execute(
                "SELECT p_mastery, n_attempts, n_correct FROM concept_knowledge WHERE concept_id = ?",
                (concept_id,),
            ).fetchone()
            if row is None:
                continue
            accuracy = max(0.0, min(1.0, evidence.correct_count / max(1, evidence.usage_count)))
            initial_mastery = accuracy * 0.7
            p_mastery = max(float(row["p_mastery"] or 0.0), initial_mastery)
            n_attempts = max(int(row["n_attempts"] or 0), evidence.usage_count)
            n_correct = max(int(row["n_correct"] or 0), evidence.correct_count)
            conn.execute(
                """
                UPDATE concept_knowledge
                SET p_mastery = ?, n_attempts = ?, n_correct = ?, teach_shown = 1, updated_at = ?
                WHERE concept_id = ?
                """,
                (p_mastery, n_attempts, n_correct, timestamp, concept_id),
            )
            demonstrated.append(concept_id)

        conn.commit()

    return {
        "safe_tier": safe_tier,
        "unlocked_count": unlocked_count,
        "demonstrated_concepts": sorted(set(demonstrated)),
        "estimated_cefr": cefr,
    }


def _cefr_to_tier(level: str) -> int:
    normalized = level.strip().upper()
    if normalized.startswith("A1"):
        return 1
    if normalized.startswith("A2"):
        return 2
    if normalized.startswith("B"):
        return 3
    return 1
