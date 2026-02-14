"""Tests for flow_db.py: session CRUD, responses, skill profile, concept knowledge, MCQ cache."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def fresh_db(tmp_path):
    """Use a temp file DB for each test."""
    from spanish_vibes import db
    db_path = tmp_path / "test.db"
    db.DB_PATH = db_path
    db.init_db()
    yield
    if db_path.exists():
        db_path.unlink()


from spanish_vibes.flow_db import (
    create_session,
    end_session,
    get_active_session,
    get_or_create_flow_state,
    get_session,
    get_session_responses,
    get_weak_lessons,
    record_response,
    update_flow_state,
    update_session,
    update_skill_profile,
    save_ai_card,
    get_cached_ai_card,
    create_conversation,
    add_conversation_turn,
    get_conversation,
    complete_conversation,
    get_recent_card_ids,
    get_all_concept_knowledge,
    get_concept_knowledge,
    update_concept_knowledge,
    mark_teach_shown,
    get_cached_mcqs,
    save_mcq_batch,
    increment_mcq_usage,
    count_cached_mcqs,
    store_vocabulary_gap,
)


def _seed_concepts():
    """Seed a few concepts for testing."""
    from spanish_vibes.db import _open_connection, now_iso
    timestamp = now_iso()
    with _open_connection() as conn:
        for cid in ["greetings", "numbers", "pronouns"]:
            conn.execute(
                "INSERT OR REPLACE INTO concepts (id, name, description, difficulty_level, teach_content, created_at) VALUES (?, ?, '', 1, 'test', ?)",
                (cid, cid.title(), timestamp),
            )
            conn.execute(
                "INSERT OR IGNORE INTO concept_knowledge (concept_id, p_mastery, n_attempts, n_correct, n_wrong, teach_shown, updated_at) VALUES (?, 0.0, 0, 0, 0, 0, ?)",
                (cid, timestamp),
            )
        conn.commit()


class TestSessionCRUD:
    def test_create_and_get(self):
        session = create_session(1000.0)
        assert session.id is not None
        assert session.status == "active"
        assert session.flow_score == 1000.0

        fetched = get_session(session.id)
        assert fetched is not None
        assert fetched.id == session.id

    def test_update_session(self):
        session = create_session(1000.0)
        update_session(session.id, cards_answered=5, correct_count=3, flow_score=1050.0)
        fetched = get_session(session.id)
        assert fetched.cards_answered == 5
        assert fetched.correct_count == 3
        assert fetched.flow_score == 1050.0

    def test_end_session(self):
        session = create_session(1000.0)
        ended = end_session(session.id)
        assert ended is not None
        assert ended.status == "completed"
        assert ended.ended_at is not None

    def test_get_active_session(self):
        assert get_active_session() is None
        session = create_session(1000.0)
        active = get_active_session()
        assert active is not None
        assert active.id == session.id

        end_session(session.id)
        assert get_active_session() is None

    def test_get_nonexistent_session(self):
        assert get_session(9999) is None


class TestResponseRecording:
    def test_record_and_fetch(self):
        session = create_session(1000.0)
        resp_id = record_response(
            session_id=session.id,
            card_id=None,
            response_type="standard",
            prompt_json='{"prompt": "hola"}',
            user_answer="hello",
            expected_answer="hello",
            is_correct=True,
            response_time_ms=2500,
            difficulty_score=1000.0,
            flow_score_after=1016.0,
        )
        assert resp_id > 0

        responses = get_session_responses(session.id)
        assert len(responses) == 1
        assert responses[0].is_correct is True
        assert responses[0].user_answer == "hello"

    def test_record_with_concept_fields(self):
        session = create_session(1000.0)
        resp_id = record_response(
            session_id=session.id,
            card_id=None,
            response_type="mcq",
            prompt_json="{}",
            user_answer="gato",
            expected_answer="gato",
            is_correct=True,
            response_time_ms=1500,
            difficulty_score=1.0,
            flow_score_after=1000.0,
            concept_id="animals_vocab",
            chosen_option="gato",
            misconception_concept=None,
        )
        assert resp_id > 0

    def test_recent_card_ids(self):
        session = create_session(1000.0)
        for i in range(5):
            record_response(
                session_id=session.id,
                card_id=None,
                response_type="standard",
                prompt_json="{}",
                user_answer="x",
                expected_answer="x",
                is_correct=True,
                response_time_ms=None,
                difficulty_score=1000.0,
                flow_score_after=1000.0,
            )
        # No card_ids set so should be empty
        recent = get_recent_card_ids(session.id, limit=3)
        assert len(recent) == 0


class TestFlowState:
    def test_get_or_create(self):
        state = get_or_create_flow_state()
        assert state["current_flow_score"] == 1000.0
        assert state["total_sessions"] == 0

    def test_update(self):
        get_or_create_flow_state()
        update_flow_state(current_flow_score=1100.0, total_sessions_increment=1, total_cards_increment=10)
        state = get_or_create_flow_state()
        assert state["current_flow_score"] == 1100.0
        assert state["total_sessions"] == 1
        assert state["total_cards"] == 10


class TestSkillProfile:
    def _create_lesson(self) -> int:
        from spanish_vibes.db import get_or_create_lesson
        return get_or_create_lesson("ch01-01-test", "Test", 1, "easy")

    def test_first_attempt(self):
        lid = self._create_lesson()
        update_skill_profile(lid, "vocab", True, 2000)
        weak = get_weak_lessons(limit=10)
        # Need at least 2 attempts to show in weak list
        assert len(weak) == 0

    def test_multiple_attempts_tracked(self):
        lid = self._create_lesson()
        update_skill_profile(lid, "vocab", True, 2000)
        update_skill_profile(lid, "vocab", False, 3000)
        update_skill_profile(lid, "vocab", False, 2500)
        weak = get_weak_lessons(limit=10)
        assert len(weak) == 1
        assert weak[0]["lesson_id"] == lid
        assert weak[0]["proficiency"] < 0.5


class TestAICardCache:
    def test_save_and_get(self):
        card_id = save_ai_card(
            card_type="vocab",
            base_card_id=None,
            difficulty_score=1000.0,
            prompt="What does 'gato' mean?",
            solution="cat",
            content_hash="abc123",
        )
        assert card_id > 0

        cached = get_cached_ai_card("abc123")
        assert cached is not None
        assert cached["prompt"] == "What does 'gato' mean?"

    def test_duplicate_hash_increments_usage(self):
        id1 = save_ai_card(
            card_type="vocab", base_card_id=None, difficulty_score=1000.0,
            prompt="test", solution="test", content_hash="dup123",
        )
        id2 = save_ai_card(
            card_type="vocab", base_card_id=None, difficulty_score=1000.0,
            prompt="test", solution="test", content_hash="dup123",
        )
        assert id1 == id2

    def test_missing_hash(self):
        assert get_cached_ai_card("nonexistent") is None


class TestConversations:
    def test_create_and_add_turns(self):
        session = create_session(1000.0)
        conv_id = create_conversation(session.id, "food")
        assert conv_id > 0

        result = add_conversation_turn(conv_id, "assistant", "Hola, que quieres comer?")
        assert result["turn_count"] == 0  # assistant turns don't count

        result = add_conversation_turn(conv_id, "user", "Quiero pizza")
        assert result["turn_count"] == 1

        conv = get_conversation(conv_id)
        assert conv is not None
        assert len(conv["messages"]) == 2
        assert conv["completed"] == 0

    def test_complete_conversation(self):
        session = create_session(1000.0)
        conv_id = create_conversation(session.id, "food")
        complete_conversation(conv_id)
        conv = get_conversation(conv_id)
        assert conv["completed"] == 1

    def test_nonexistent_conversation(self):
        assert get_conversation(9999) is None


class TestConceptKnowledge:
    def test_get_all_empty(self):
        knowledge = get_all_concept_knowledge()
        assert isinstance(knowledge, dict)

    def test_get_all_with_data(self):
        _seed_concepts()
        knowledge = get_all_concept_knowledge()
        assert len(knowledge) == 3
        assert "greetings" in knowledge
        assert knowledge["greetings"].p_mastery == 0.0

    def test_get_single(self):
        _seed_concepts()
        ck = get_concept_knowledge("greetings")
        assert ck is not None
        assert ck.concept_id == "greetings"
        assert ck.n_attempts == 0

    def test_get_nonexistent(self):
        assert get_concept_knowledge("nonexistent") is None

    def test_update_correct(self):
        _seed_concepts()
        update_concept_knowledge("greetings", 0.15, True)
        ck = get_concept_knowledge("greetings")
        assert ck.p_mastery == 0.15
        assert ck.n_attempts == 1
        assert ck.n_correct == 1
        assert ck.n_wrong == 0

    def test_update_wrong(self):
        _seed_concepts()
        update_concept_knowledge("greetings", 0.05, False)
        ck = get_concept_knowledge("greetings")
        assert ck.p_mastery == 0.05
        assert ck.n_attempts == 1
        assert ck.n_correct == 0
        assert ck.n_wrong == 1

    def test_mark_teach_shown(self):
        _seed_concepts()
        ck = get_concept_knowledge("greetings")
        assert ck.teach_shown is False
        mark_teach_shown("greetings")
        ck = get_concept_knowledge("greetings")
        assert ck.teach_shown is True


class TestMCQCache:
    def test_save_and_get(self):
        _seed_concepts()
        ids = save_mcq_batch("greetings", [
            {
                "question": "What does 'hola' mean?",
                "correct_answer": "hello",
                "distractors": [
                    {"text": "goodbye", "misconception": "greetings"},
                    {"text": "thanks", "misconception": "greetings"},
                    {"text": "please", "misconception": "greetings"},
                ],
                "difficulty": 1,
                "source": "ai",
                "content_hash": "mcq_hash_1",
            },
        ])
        assert len(ids) == 1

        mcqs = get_cached_mcqs("greetings")
        assert len(mcqs) == 1
        assert mcqs[0].question == "What does 'hola' mean?"
        assert mcqs[0].correct_answer == "hello"
        assert len(mcqs[0].distractors) == 3

    def test_duplicate_hash_deduped(self):
        _seed_concepts()
        card = {
            "question": "test",
            "correct_answer": "test",
            "distractors": [],
            "content_hash": "dup_mcq",
        }
        ids1 = save_mcq_batch("greetings", [card])
        ids2 = save_mcq_batch("greetings", [card])
        assert ids1 == ids2

    def test_increment_usage(self):
        _seed_concepts()
        ids = save_mcq_batch("greetings", [
            {
                "question": "test",
                "correct_answer": "test",
                "distractors": [],
                "content_hash": "usage_test",
            },
        ])
        increment_mcq_usage(ids[0])
        mcqs = get_cached_mcqs("greetings")
        assert mcqs[0].times_used == 1

    def test_count_cached(self):
        _seed_concepts()
        assert count_cached_mcqs("greetings") == 0
        save_mcq_batch("greetings", [
            {"question": "q1", "correct_answer": "a1", "distractors": [], "content_hash": "h1"},
            {"question": "q2", "correct_answer": "a2", "distractors": [], "content_hash": "h2"},
        ])
        assert count_cached_mcqs("greetings") == 2

    def test_exclude_ids(self):
        _seed_concepts()
        ids = save_mcq_batch("greetings", [
            {"question": "q1", "correct_answer": "a1", "distractors": [], "content_hash": "ex1"},
            {"question": "q2", "correct_answer": "a2", "distractors": [], "content_hash": "ex2"},
        ])
        mcqs = get_cached_mcqs("greetings", exclude_ids=[ids[0]])
        assert len(mcqs) == 1
        assert mcqs[0].id == ids[1]

class TestVocabularyGapStorage:
    def test_store_gap_upserts(self):
        from spanish_vibes.db import _open_connection

        store_vocabulary_gap("store", "tienda", "shopping")
        store_vocabulary_gap("store", "tienda", "shopping")

        with _open_connection() as conn:
            row = conn.execute(
                "SELECT english_word, spanish_word, concept_id, times_seen FROM vocabulary_gaps WHERE english_word = ?",
                ("store",),
            ).fetchone()
            word_row = conn.execute(
                "SELECT spanish, english, status FROM words WHERE spanish = ?",
                ("tienda",),
            ).fetchone()

        assert row is not None
        assert row["spanish_word"] == "tienda"
        assert row["concept_id"] == "shopping"
        assert row["times_seen"] == 2
        assert word_row is not None
        assert word_row["english"] == "store"
