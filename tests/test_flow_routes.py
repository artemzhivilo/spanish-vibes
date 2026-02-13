"""Tests for flow_routes.py v2: route integration tests for MCQ-based flow."""

from __future__ import annotations

import json

import pytest


@pytest.fixture(autouse=True)
def fresh_db(tmp_path):
    from spanish_vibes import db
    db_path = tmp_path / "test.db"
    db.DB_PATH = db_path
    db.init_db()
    from spanish_vibes.concepts import clear_cache
    clear_cache()
    yield
    if db_path.exists():
        db_path.unlink()


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from spanish_vibes.app import app
    return TestClient(app)


def _seed_flow_data():
    """Seed concepts + MCQ cache for flow route testing."""
    from spanish_vibes.concepts import seed_concepts_to_db, CONCEPTS_FILE
    if CONCEPTS_FILE.exists():
        seed_concepts_to_db()

    from spanish_vibes.flow_db import save_mcq_batch
    save_mcq_batch("greetings", [
        {
            "question": "What does 'hola' mean?",
            "correct_answer": "hello",
            "distractors": [
                {"text": "goodbye", "misconception": "greetings"},
                {"text": "thanks", "misconception": "greetings"},
                {"text": "please", "misconception": "greetings"},
            ],
            "difficulty": 1,
            "content_hash": "route_test_mcq_1",
        },
    ])


class TestFlowPage:
    def test_get_flow_page(self, client):
        _seed_flow_data()
        response = client.get("/flow")
        assert response.status_code == 200
        assert "Flow" in response.text

    def test_flow_shows_concept_progress(self, client):
        _seed_flow_data()
        response = client.get("/flow")
        assert response.status_code == 200
        assert "mastered" in response.text


class TestFlowCard:
    def test_get_card_returns_teach_or_mcq(self, client):
        _seed_flow_data()
        client.get("/flow")

        from spanish_vibes.flow_db import get_active_session
        session = get_active_session()
        assert session is not None

        response = client.get(f"/flow/card?session_id={session.id}")
        assert response.status_code == 200
        # Should have teach card (New Concept) or MCQ options
        assert "Got it" in response.text or "New Concept" in response.text or "Back" in response.text

    def test_get_card_no_data(self, client):
        # No concepts seeded
        client.get("/flow")
        from spanish_vibes.flow_db import get_active_session
        session = get_active_session()
        response = client.get(f"/flow/card?session_id={session.id}")
        assert response.status_code == 200


class TestFlowTeachSeen:
    def test_teach_seen_advances(self, client):
        _seed_flow_data()
        client.get("/flow")
        from spanish_vibes.flow_db import get_active_session
        session = get_active_session()

        response = client.post("/flow/teach-seen", data={
            "session_id": session.id,
            "concept_id": "greetings",
        })
        assert response.status_code == 200

        # Verify teach was marked
        from spanish_vibes.flow_db import get_concept_knowledge
        ck = get_concept_knowledge("greetings")
        assert ck.teach_shown is True


class TestFlowAnswer:
    def test_submit_correct_mcq(self, client):
        _seed_flow_data()
        # Mark teach shown so we get MCQ
        from spanish_vibes.flow_db import mark_teach_shown, update_concept_knowledge
        mark_teach_shown("greetings")
        update_concept_knowledge("greetings", 0.15, True)

        client.get("/flow")
        from spanish_vibes.flow_db import get_active_session
        session = get_active_session()

        card_json = json.dumps({
            "card_type": "mcq",
            "concept_id": "greetings",
            "question": "What does 'hola' mean?",
            "correct_answer": "hello",
            "options": ["hello", "goodbye", "thanks", "please"],
            "option_misconceptions": {"goodbye": "greetings"},
            "difficulty": 1,
            "mcq_card_id": 1,
        })

        response = client.post("/flow/answer", data={
            "session_id": session.id,
            "chosen_option": "hello",
            "card_json": card_json,
            "start_time": 0,
        })
        assert response.status_code == 200
        assert "Correct" in response.text

    def test_submit_wrong_mcq(self, client):
        _seed_flow_data()
        from spanish_vibes.flow_db import mark_teach_shown, update_concept_knowledge
        mark_teach_shown("greetings")
        update_concept_knowledge("greetings", 0.15, True)

        client.get("/flow")
        from spanish_vibes.flow_db import get_active_session
        session = get_active_session()

        card_json = json.dumps({
            "card_type": "mcq",
            "concept_id": "greetings",
            "question": "What does 'hola' mean?",
            "correct_answer": "hello",
            "options": ["hello", "goodbye", "thanks", "please"],
            "option_misconceptions": {"goodbye": "greetings"},
            "difficulty": 1,
            "mcq_card_id": 1,
        })

        response = client.post("/flow/answer", data={
            "session_id": session.id,
            "chosen_option": "goodbye",
            "card_json": card_json,
            "start_time": 0,
        })
        assert response.status_code == 200
        assert "Not quite" in response.text or "Got it" in response.text


class TestFlowEnd:
    def test_end_session(self, client):
        _seed_flow_data()
        client.get("/flow")
        from spanish_vibes.flow_db import get_active_session
        session = get_active_session()

        response = client.post("/flow/end", data={
            "session_id": session.id,
        })
        assert response.status_code == 200
        assert "Complete" in response.text or "Session" in response.text
