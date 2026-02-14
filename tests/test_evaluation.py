from __future__ import annotations

import pytest

from spanish_vibes import db
from spanish_vibes.conversation import ConversationMessage
from spanish_vibes.db import _open_connection, init_db
from spanish_vibes.evaluation import compute_enjoyment_score, update_persona_engagement


@pytest.fixture(autouse=True)
def _setup_db(tmp_path):
    db.DB_PATH = tmp_path / "test.db"
    init_db()


def _messages_from_user_texts(texts: list[str]) -> list[ConversationMessage]:
    messages: list[ConversationMessage] = [ConversationMessage(role="ai", content="hola")]
    for text in texts:
        messages.append(ConversationMessage(role="user", content=text))
        messages.append(ConversationMessage(role="ai", content="vale"))
    return messages


def test_compute_enjoyment_score_high_engagement():
    msgs = _messages_from_user_texts(
        [
            "hoy practico espanol con frases largas porque quiero mejorar rapido",
            "me gusta hablar de viajes y tambien de comida tradicional con detalles",
            "normalmente escribo respuestas completas cuando la conversacion es interesante",
            "esta actividad me ayuda mucho porque puedo usar vocabulario nuevo cada turno",
        ]
    )
    score = compute_enjoyment_score(msgs, max_turns=4, engagement_quality_from_llm=0.9)
    assert score >= 0.8


def test_compute_enjoyment_score_low_engagement():
    msgs = _messages_from_user_texts(["si", "no"])
    score = compute_enjoyment_score(msgs, max_turns=4, engagement_quality_from_llm=0.2)
    assert score <= 0.3


def test_compute_enjoyment_score_mixed_engagement():
    msgs = _messages_from_user_texts(
        [
            "hoy estudio un poco",
            "quiero practicar mas verbos",
            "esta parte fue dificil",
        ]
    )
    score = compute_enjoyment_score(msgs, max_turns=4, engagement_quality_from_llm=0.5)
    assert 0.35 <= score <= 0.65


def test_update_persona_engagement_updates_topic_and_persona_rows():
    update_persona_engagement(
        persona_id="diego",
        topic_id=7,
        enjoyment_score=0.8,
        avg_message_length=8.0,
        turn_count=6,
        was_early_exit=False,
    )
    update_persona_engagement(
        persona_id="diego",
        topic_id=7,
        enjoyment_score=0.2,
        avg_message_length=2.0,
        turn_count=2,
        was_early_exit=True,
    )

    with _open_connection() as conn:
        rows = conn.execute(
            """
            SELECT topic_id, conversation_count, avg_enjoyment_score, avg_message_length,
                   avg_turns, early_exit_rate
            FROM persona_engagement
            WHERE persona_id = ?
            ORDER BY topic_id IS NULL, topic_id
            """,
            ("diego",),
        ).fetchall()

    assert len(rows) == 2
    for row in rows:
        assert int(row["conversation_count"]) == 2
        assert pytest.approx(float(row["avg_enjoyment_score"]), abs=1e-6) == 0.5
        assert pytest.approx(float(row["avg_message_length"]), abs=1e-6) == 5.0
        assert pytest.approx(float(row["avg_turns"]), abs=1e-6) == 4.0
        assert pytest.approx(float(row["early_exit_rate"]), abs=1e-6) == 0.5
