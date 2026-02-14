from __future__ import annotations

from datetime import datetime, timezone
import random

import pytest

from spanish_vibes import db
from spanish_vibes.db import _open_connection, init_db, now_iso
from spanish_vibes.personas import Persona, get_persona_prompt, load_all_personas, load_persona, select_persona


@pytest.fixture(autouse=True)
def _setup_db(tmp_path):
    db.DB_PATH = tmp_path / "test.db"
    init_db()


def test_load_all_personas_includes_defaults():
    personas = load_all_personas()
    ids = {p.id for p in personas}
    assert {"marta", "diego", "abuela_rosa", "luis"}.issubset(ids)


def test_load_persona_fallback():
    persona = load_persona(None)
    assert persona.name
    assert get_persona_prompt(persona)


def test_select_persona_returns_valid():
    persona = select_persona()
    assert persona.id
    assert persona.name
    assert isinstance(get_persona_prompt(persona), str)


def test_select_persona_weighted_prefers_high_engagement(monkeypatch: pytest.MonkeyPatch):
    personas = [
        Persona(id="high", name="High", system_prompt="A"),
        Persona(id="low", name="Low", system_prompt="B"),
    ]
    monkeypatch.setattr("spanish_vibes.personas.load_all_personas", lambda: personas)
    monkeypatch.setattr(random, "random", lambda: 0.5)

    with _open_connection() as conn:
        now = now_iso(datetime.now(timezone.utc))
        conn.execute(
            """
            INSERT INTO persona_engagement (persona_id, topic_id, conversation_count, avg_enjoyment_score, last_conversation_at)
            VALUES (?, NULL, ?, ?, ?)
            """,
            ("high", 20, 0.95, now),
        )
        conn.execute(
            """
            INSERT INTO persona_engagement (persona_id, topic_id, conversation_count, avg_enjoyment_score, last_conversation_at)
            VALUES (?, NULL, ?, ?, ?)
            """,
            ("low", 20, 0.10, now),
        )
        conn.commit()

    picks = [select_persona().id for _ in range(200)]
    assert picks.count("high") > picks.count("low")


def test_select_persona_excludes_last_persona(monkeypatch: pytest.MonkeyPatch):
    personas = [
        Persona(id="one", name="One", system_prompt="A"),
        Persona(id="two", name="Two", system_prompt="B"),
    ]
    monkeypatch.setattr("spanish_vibes.personas.load_all_personas", lambda: personas)
    for _ in range(30):
        assert select_persona(exclude_id="one").id == "two"


def test_select_persona_new_persona_gets_trials(monkeypatch: pytest.MonkeyPatch):
    personas = [
        Persona(id="known", name="Known", system_prompt="A"),
        Persona(id="new", name="New", system_prompt="B"),
    ]
    monkeypatch.setattr("spanish_vibes.personas.load_all_personas", lambda: personas)
    monkeypatch.setattr(random, "random", lambda: 0.0)

    with _open_connection() as conn:
        conn.execute(
            """
            INSERT INTO persona_engagement (
                persona_id, topic_id, conversation_count, avg_enjoyment_score,
                avg_message_length, avg_turns, early_exit_rate, last_conversation_at
            )
            VALUES (?, NULL, 10, 0.2, 2.0, 3.0, 0.4, ?)
            """,
            ("known", now_iso()),
        )
        conn.commit()

    picks = [select_persona().id for _ in range(100)]
    assert "new" in picks
