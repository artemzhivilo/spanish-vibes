from __future__ import annotations

from collections import Counter

import pytest

from spanish_vibes import db
from spanish_vibes.db import _open_connection, init_db
from spanish_vibes.conversation_types import get_type_instruction, select_conversation_type
from spanish_vibes.flow_ai import generate_story_card


@pytest.fixture(autouse=True)
def _setup_db(tmp_path):
    db.DB_PATH = tmp_path / "test.db"
    init_db()
    from spanish_vibes.concepts import CONCEPTS_FILE, seed_concepts_to_db
    if CONCEPTS_FILE.exists():
        seed_concepts_to_db()


def test_select_conversation_type_distribution_is_reasonable():
    counts: Counter[str] = Counter()
    for _ in range(100):
        conv_type, _target = select_conversation_type("greetings", session_id=1)
        counts[conv_type] += 1

    assert sum(counts.values()) == 100
    assert counts["general_chat"] >= 25
    assert all(
        conv_type in {"general_chat", "role_play", "concept_required", "tutor", "story_comprehension"}
        for conv_type in counts
    )


def test_stuck_concept_forces_concept_required():
    with _open_connection() as conn:
        row = conn.execute(
            "SELECT concept_id FROM concept_knowledge ORDER BY concept_id LIMIT 1"
        ).fetchone()
        assert row is not None
        concept_id = str(row["concept_id"])
        conn.execute(
            """
            UPDATE concept_knowledge
            SET p_mastery = 0.45, n_attempts = 8, n_correct = 3, n_wrong = 5
            WHERE concept_id = ?
            """,
            (concept_id,),
        )
        conn.commit()

    conv_type, target = select_conversation_type(concept_id, session_id=1)
    assert conv_type == "concept_required"
    assert target == concept_id


def test_get_type_instruction_role_play_contains_scenario():
    instruction = get_type_instruction(
        "role_play",
        concept_id="greetings",
        topic="travel",
        persona_id="marta",
    )
    assert instruction is not None
    assert "CONVERSATION MODE: Role Play" in instruction
    assert "SCENARIO:" in instruction


def test_flow_conversations_has_conversation_type_column():
    with _open_connection() as conn:
        cols = conn.execute("PRAGMA table_info(flow_conversations)").fetchall()
    names = {str(row["name"]) for row in cols}
    assert "conversation_type" in names


def test_generate_story_card_fallback_shape():
    payload = generate_story_card(
        concept_id="greetings",
        topic="travel",
        difficulty=1,
        persona_prompt="Friendly and brief.",
        persona_name="Marta",
    )
    assert isinstance(payload, dict)
    assert isinstance(payload.get("story"), str)
    questions = payload.get("questions")
    assert isinstance(questions, list)
    assert len(questions) >= 2
    assert "question" in questions[0]
    assert "correct_answer" in questions[0]
    assert "options" in questions[0]
