"""Tests for flow.py v2: concept-based BKT scheduler, MCQ card selection."""

from __future__ import annotations

import pytest

from spanish_vibes.flow import (
    FlowAnswerResult,
    FlowSessionState,
    _pick_concept,
    build_session_state,
    end_flow_session,
    process_mcq_answer,
    select_next_card,
    start_or_resume_session,
)
from spanish_vibes.models import ConceptKnowledge, FlowCardContext


@pytest.fixture(autouse=True)
def fresh_db(tmp_path):
    from spanish_vibes import db
    db.DB_PATH = tmp_path / "test.db"
    db.init_db()
    from spanish_vibes.concepts import clear_cache
    clear_cache()
    yield


def _seed_concepts_and_mcqs():
    """Seed concepts from YAML + MCQ cache for testing."""
    from spanish_vibes.concepts import seed_concepts_to_db, CONCEPTS_FILE
    from spanish_vibes.flow_db import save_mcq_batch

    if CONCEPTS_FILE.exists():
        seed_concepts_to_db()

    # Add MCQ cards for greetings
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
            "content_hash": "test_mcq_1",
        },
        {
            "question": "What does 'adiós' mean?",
            "correct_answer": "goodbye",
            "distractors": [
                {"text": "hello", "misconception": "greetings"},
                {"text": "thanks", "misconception": "greetings"},
                {"text": "please", "misconception": "greetings"},
            ],
            "difficulty": 1,
            "content_hash": "test_mcq_2",
        },
    ])


class TestPickConcept:
    def test_returns_none_when_empty(self):
        assert _pick_concept([], [], [], {}) is None

    def test_returns_from_new_when_only_bucket(self):
        result = _pick_concept([], [], ["greetings"], {})
        assert result == "greetings"

    def test_returns_from_learning_when_only_bucket(self):
        knowledge = {
            "greetings": ConceptKnowledge(
                concept_id="greetings", p_mastery=0.3, n_attempts=3,
                n_correct=2, n_wrong=1, teach_shown=True, last_seen_at=None,
            ),
        }
        result = _pick_concept([], ["greetings"], [], knowledge)
        assert result == "greetings"

    def test_returns_from_some_bucket(self):
        knowledge = {
            "greetings": ConceptKnowledge(
                concept_id="greetings", p_mastery=0.95, n_attempts=10,
                n_correct=9, n_wrong=1, teach_shown=True, last_seen_at=None,
            ),
        }
        result = _pick_concept(["greetings"], ["numbers"], ["colors"], knowledge)
        assert result in ("greetings", "numbers", "colors")


class TestSelectNextCard:
    def test_returns_teach_card_for_new_concept(self):
        _seed_concepts_and_mcqs()
        session = start_or_resume_session()
        card = select_next_card(session.id)
        # Should get a teach card since no concepts have been attempted
        assert card is not None
        assert card.card_type == "teach"
        assert card.teach_content

    def test_returns_mcq_after_teach_shown(self):
        _seed_concepts_and_mcqs()
        # Mark teach as shown and add an attempt
        from spanish_vibes.flow_db import mark_teach_shown, update_concept_knowledge
        mark_teach_shown("greetings")
        update_concept_knowledge("greetings", 0.15, True)

        session = start_or_resume_session()
        card = select_next_card(session.id)
        # Should get MCQ or teach for another concept
        assert card is not None

    def test_returns_none_when_no_data(self):
        # No concepts seeded
        session = start_or_resume_session()
        card = select_next_card(session.id)
        assert card is None


class TestProcessMCQAnswer:
    def test_correct_answer(self):
        _seed_concepts_and_mcqs()
        # Mark teach shown and add attempt so we get MCQ
        from spanish_vibes.flow_db import mark_teach_shown, update_concept_knowledge
        mark_teach_shown("greetings")
        update_concept_knowledge("greetings", 0.15, True)

        session = start_or_resume_session()
        card = FlowCardContext(
            card_type="mcq",
            concept_id="greetings",
            question="What does 'hola' mean?",
            correct_answer="hello",
            options=["hello", "goodbye", "thanks", "please"],
            option_misconceptions={"goodbye": "greetings"},
            difficulty=1,
            mcq_card_id=1,
        )

        result = process_mcq_answer(
            session_id=session.id,
            card_context=card,
            chosen_option="hello",
        )
        assert result.is_correct is True
        assert result.xp_earned > 0
        assert result.streak == 1

    def test_wrong_answer(self):
        _seed_concepts_and_mcqs()
        from spanish_vibes.flow_db import mark_teach_shown, update_concept_knowledge
        mark_teach_shown("greetings")
        update_concept_knowledge("greetings", 0.15, True)

        session = start_or_resume_session()
        card = FlowCardContext(
            card_type="mcq",
            concept_id="greetings",
            question="What does 'hola' mean?",
            correct_answer="hello",
            options=["hello", "goodbye", "thanks", "please"],
            option_misconceptions={"goodbye": "greetings"},
            difficulty=1,
            mcq_card_id=1,
        )

        result = process_mcq_answer(
            session_id=session.id,
            card_context=card,
            chosen_option="goodbye",
        )
        assert result.is_correct is False
        assert result.xp_earned == 0
        assert result.streak == 0
        assert result.misconception_concept == "greetings"

    def test_mastery_tracking(self):
        _seed_concepts_and_mcqs()
        from spanish_vibes.flow_db import mark_teach_shown, update_concept_knowledge, get_concept_knowledge
        mark_teach_shown("greetings")
        update_concept_knowledge("greetings", 0.15, True)

        session = start_or_resume_session()
        card = FlowCardContext(
            card_type="mcq",
            concept_id="greetings",
            question="test",
            correct_answer="hello",
            options=["hello"],
            difficulty=1,
            mcq_card_id=1,
        )

        # Answer correctly multiple times
        for _ in range(5):
            process_mcq_answer(
                session_id=session.id,
                card_context=card,
                chosen_option="hello",
            )

        ck = get_concept_knowledge("greetings")
        # p_mastery should have increased
        assert ck.p_mastery > 0.5
        assert ck.n_correct > 5  # original + 5 more


class TestStartOrResumeSession:
    def test_creates_new_session(self):
        session = start_or_resume_session()
        assert session.status == "active"

    def test_resumes_existing(self):
        s1 = start_or_resume_session()
        s2 = start_or_resume_session()
        assert s1.id == s2.id


class TestEndFlowSession:
    def test_end_session(self):
        session = start_or_resume_session()
        ended = end_flow_session(session.id)
        assert ended is not None
        assert ended.status == "completed"
