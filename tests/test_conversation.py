"""Tests for conversation card engine."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from spanish_vibes import db
from spanish_vibes.db import init_db, _open_connection, now_iso
from spanish_vibes.conversation import (
    ConversationCard,
    ConversationEngine,
    ConversationMessage,
    ConversationSummary,
    Correction,
    EvaluationResult,
    get_random_topic,
    _detect_language,
    _explode_corrections,
)


@pytest.fixture(autouse=True)
def _setup_db(tmp_path):
    db.DB_PATH = tmp_path / "test.db"
    init_db()


# ── Opener generation ────────────────────────────────────────────────────────


class TestGenerateOpener:
    def test_fallback_opener_includes_topic(self):
        engine = ConversationEngine()
        with patch("spanish_vibes.conversation.ai_available", return_value=False):
            opener = engine.generate_opener("fútbol", "present_tense", 1)
        assert "fútbol" in opener.lower()

    def test_fallback_opener_varies_by_difficulty(self):
        engine = ConversationEngine()
        with patch("spanish_vibes.conversation.ai_available", return_value=False):
            o1 = engine.generate_opener("música", "greetings", 1)
            o2 = engine.generate_opener("música", "greetings", 2)
            o3 = engine.generate_opener("música", "greetings", 3)
        # All should contain the topic
        assert "música" in o1
        assert "música" in o2
        assert "música" in o3
        # At least two should differ
        assert len({o1, o2, o3}) >= 2

    @patch("spanish_vibes.conversation.ai_available", return_value=True)
    @patch("spanish_vibes.conversation._get_client")
    def test_ai_opener_includes_concept_in_prompt(self, mock_get_client, _mock_ai):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "¡Hola! ¿Qué haces hoy?"
        mock_client.chat.completions.create.return_value = mock_response

        engine = ConversationEngine()
        opener = engine.generate_opener("deportes", "present_tense", 1)

        assert opener == "¡Hola! ¿Qué haces hoy?"

        # Verify the prompt mentions the concept
        call_args = mock_client.chat.completions.create.call_args
        messages = call_args.kwargs.get("messages") or call_args[1].get("messages")
        system_prompt = messages[0]["content"]
        # The concept name should appear (resolved or raw)
        assert "present_tense" in system_prompt.lower() or "Present" in system_prompt


# ── Error detection ──────────────────────────────────────────────────────────


class TestEvaluateResponse:
    def test_returns_no_corrections_without_ai(self):
        engine = ConversationEngine()
        with patch("spanish_vibes.conversation.ai_available", return_value=False):
            result = engine.evaluate_response(
                "Yo tengo un gato.", "present_tense", 1
            )
        assert result.is_grammatically_correct is True
        assert result.corrections == []
        assert result.recast == "Yo tengo un gato."

    @patch("spanish_vibes.conversation.ai_available", return_value=True)
    @patch("spanish_vibes.conversation._get_client")
    def test_detects_common_a2_mistakes(self, mock_get_client, _mock_ai):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        # Simulate AI detecting a ser/estar error
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "is_correct": False,
            "recast": "Yo estoy cansado hoy.",
            "corrections": [
                {
                    "original": "Yo soy cansado",
                    "corrected": "Yo estoy cansado",
                    "explanation": "Use 'estar' for temporary states like being tired.",
                    "concept_id": "ser_estar",
                }
            ],
        })
        mock_client.chat.completions.create.return_value = mock_response

        engine = ConversationEngine()
        result = engine.evaluate_response("Yo soy cansado hoy.", "ser_estar", 2)

        assert result.is_grammatically_correct is False
        assert len(result.corrections) == 1
        assert result.corrections[0].original.strip().endswith("soy")
        assert result.corrections[0].corrected.strip().endswith("estoy")
        assert "estar" in result.corrections[0].explanation.lower()


# ── Recast technique ─────────────────────────────────────────────────────────


class TestRecastTechnique:
    @patch("spanish_vibes.conversation.ai_available", return_value=True)
    @patch("spanish_vibes.conversation._get_client")
    def test_recast_reformulates_without_explicit_error_language(self, mock_get_client, _mock_ai):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        # AI reply should NOT contain "you made an error" or similar
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = (
            "¡Sí, yo estoy cansado también! ¿Qué hiciste hoy?"
        )
        mock_client.chat.completions.create.return_value = mock_response

        engine = ConversationEngine()
        messages = [
            ConversationMessage(role="ai", content="¡Hola! ¿Cómo estás?"),
            ConversationMessage(role="user", content="Yo soy cansado."),
        ]
        reply = engine.generate_reply(messages, "la vida", "ser_estar", 1)

        # The reply should NOT contain explicit correction language
        lower_reply = reply.lower()
        assert "error" not in lower_reply
        assert "mistake" not in lower_reply
        assert "wrong" not in lower_reply
        assert "incorrect" not in lower_reply
        # But it should include the recast (correct form)
        assert "estoy" in lower_reply

    @patch("spanish_vibes.conversation.ai_available", return_value=True)
    @patch("spanish_vibes.conversation._get_client")
    def test_reply_prompt_instructs_recast(self, mock_get_client, _mock_ai):
        """Verify the system prompt tells the AI to use RECAST technique."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "¡Genial!"
        mock_client.chat.completions.create.return_value = mock_response

        engine = ConversationEngine()
        messages = [
            ConversationMessage(role="ai", content="¡Hola!"),
            ConversationMessage(role="user", content="Hola"),
        ]
        engine.generate_reply(messages, "deportes", "greetings", 1)

        call_args = mock_client.chat.completions.create.call_args
        msgs = call_args.kwargs.get("messages") or call_args[1].get("messages")
        system_prompt = msgs[0]["content"]
        assert "RECAST" in system_prompt
        assert "NOT a teacher" in system_prompt


# ── Conversation ending ──────────────────────────────────────────────────────


class TestShouldEnd:
    def test_ends_at_max_user_turns(self):
        """max_turns=4 means 4 USER messages trigger end."""
        engine = ConversationEngine()
        card = ConversationCard(
            topic="deportes",
            concept="present_tense",
            difficulty=1,
            opener="¡Hola!",
            max_turns=4,
            messages=[
                ConversationMessage(role="ai", content="¡Hola!"),
                ConversationMessage(role="user", content="Hola"),
                ConversationMessage(role="ai", content="¿Qué tal?"),
                ConversationMessage(role="user", content="Bien"),
                ConversationMessage(role="ai", content="¡Genial!"),
                ConversationMessage(role="user", content="Sí"),
                ConversationMessage(role="ai", content="¿Y tú?"),
                ConversationMessage(role="user", content="También bien"),
            ],
        )
        assert engine.should_end(card) is True

    def test_does_not_end_before_max_user_turns(self):
        """2 user messages out of 4 required — should not end."""
        engine = ConversationEngine()
        card = ConversationCard(
            topic="deportes",
            concept="present_tense",
            difficulty=1,
            opener="¡Hola!",
            max_turns=4,
            messages=[
                ConversationMessage(role="ai", content="¡Hola!"),
                ConversationMessage(role="user", content="Hola"),
                ConversationMessage(role="ai", content="¿Qué tal?"),
                ConversationMessage(role="user", content="Bien"),
            ],
        )
        assert engine.should_end(card) is False

    def test_custom_max_turns(self):
        """max_turns=2 ends after 2 user messages."""
        engine = ConversationEngine()
        card = ConversationCard(
            topic="música",
            concept="greetings",
            difficulty=1,
            opener="¡Hola!",
            max_turns=2,
            messages=[
                ConversationMessage(role="ai", content="¡Hola!"),
                ConversationMessage(role="user", content="Hola"),
                ConversationMessage(role="ai", content="¿Qué tal?"),
                ConversationMessage(role="user", content="Bien"),
            ],
        )
        assert engine.should_end(card) is True

    def test_four_total_messages_two_user_does_not_end(self):
        """4 total messages but only 2 user turns — max_turns=4 should NOT end."""
        engine = ConversationEngine()
        card = ConversationCard(
            topic="deportes",
            concept="present_tense",
            difficulty=1,
            opener="¡Hola!",
            max_turns=4,
            messages=[
                ConversationMessage(role="ai", content="¡Hola!"),
                ConversationMessage(role="user", content="Hola"),
                ConversationMessage(role="ai", content="¿Qué tal?"),
                ConversationMessage(role="user", content="Bien"),
            ],
        )
        assert engine.should_end(card) is False


# ── Summary generation ───────────────────────────────────────────────────────


class TestGenerateSummary:
    def test_summary_includes_all_corrections(self):
        engine = ConversationEngine()
        card = ConversationCard(
            topic="deportes",
            concept="present_tense",
            difficulty=1,
            opener="¡Hola!",
            messages=[
                ConversationMessage(role="ai", content="¡Hola!"),
                ConversationMessage(
                    role="user",
                    content="Yo soy cansado.",
                    corrections=[
                        Correction(
                            original="soy cansado",
                            corrected="estoy cansado",
                            explanation="Use estar for states",
                            concept_id="ser_estar",
                        ),
                    ],
                ),
                ConversationMessage(role="ai", content="Yo estoy cansado también."),
                ConversationMessage(
                    role="user",
                    content="Yo quiero ir a el parque.",
                    corrections=[
                        Correction(
                            original="a el",
                            corrected="al",
                            explanation="a + el contracts to al",
                            concept_id="contractions",
                        ),
                    ],
                ),
            ],
        )

        summary = engine.generate_summary(card)
        assert len(summary.corrections) == 2
        assert summary.corrections[0].concept_id == "ser_estar"
        assert summary.corrections[1].concept_id == "contractions"
        assert summary.turn_count == 4

    def test_summary_score_reflects_accuracy(self):
        engine = ConversationEngine()
        # 1 correct user message, 1 with corrections → 50%
        card = ConversationCard(
            topic="comida",
            concept="greetings",
            difficulty=1,
            opener="¡Hola!",
            messages=[
                ConversationMessage(role="ai", content="¡Hola!"),
                ConversationMessage(role="user", content="¡Hola! ¿Cómo estás?"),
                ConversationMessage(role="ai", content="Bien, ¿y tú?"),
                ConversationMessage(
                    role="user",
                    content="Yo soy bien.",
                    corrections=[
                        Correction("soy bien", "estoy bien", "Use estar", "ser_estar"),
                    ],
                ),
            ],
        )

        summary = engine.generate_summary(card)
        assert summary.score == 0.5  # 1 correct out of 2 user messages

    def test_summary_perfect_score(self):
        engine = ConversationEngine()
        card = ConversationCard(
            topic="música",
            concept="greetings",
            difficulty=1,
            opener="¡Hola!",
            messages=[
                ConversationMessage(role="ai", content="¡Hola!"),
                ConversationMessage(role="user", content="¡Hola!"),
                ConversationMessage(role="ai", content="¿Qué tal?"),
                ConversationMessage(role="user", content="Bien, gracias."),
            ],
        )

        summary = engine.generate_summary(card)
        assert summary.score == 1.0
        assert summary.corrections == []

    def test_summary_concepts_include_target(self):
        engine = ConversationEngine()
        card = ConversationCard(
            topic="deportes",
            concept="present_tense",
            difficulty=1,
            opener="¡Hola!",
            messages=[
                ConversationMessage(role="ai", content="¡Hola!"),
                ConversationMessage(role="user", content="Hola"),
            ],
        )
        summary = engine.generate_summary(card)
        assert "present_tense" in summary.concepts_practiced

    def test_summary_no_user_messages(self):
        engine = ConversationEngine()
        card = ConversationCard(
            topic="test",
            concept="greetings",
            difficulty=1,
            opener="¡Hola!",
            messages=[
                ConversationMessage(role="ai", content="¡Hola!"),
            ],
        )
        summary = engine.generate_summary(card)
        assert summary.score == 0.0
        assert summary.corrections == []


# ── Message serialization ────────────────────────────────────────────────────


class TestMessageSerialization:
    def test_round_trip_without_corrections(self):
        msg = ConversationMessage(role="ai", content="¡Hola!", timestamp="2026-02-13T10:00:00Z")
        data = msg.to_dict()
        restored = ConversationMessage.from_dict(data)
        assert restored.role == "ai"
        assert restored.content == "¡Hola!"
        assert restored.corrections is None

    def test_round_trip_with_corrections(self):
        msg = ConversationMessage(
            role="user",
            content="Yo soy cansado.",
            corrections=[
                Correction("soy cansado", "estoy cansado", "Use estar", "ser_estar"),
            ],
            timestamp="2026-02-13T10:01:00Z",
        )
        data = msg.to_dict()
        restored = ConversationMessage.from_dict(data)
        assert restored.corrections is not None
        assert len(restored.corrections) == 1
        assert restored.corrections[0].original == "soy cansado"
        assert restored.corrections[0].concept_id == "ser_estar"


class TestLanguageDetection:
    def test_detect_language_english(self):
        assert _detect_language("I went to the store yesterday") == "en"

    def test_detect_language_spanish(self):
        assert _detect_language("Fui a la tienda ayer") == "es"

    def test_detect_language_mixed(self):
        assert _detect_language("I fui to the tienda") == "mixed"


class TestEnglishFallback:
    @patch("spanish_vibes.conversation.ai_available", return_value=True)
    @patch("spanish_vibes.conversation._get_client")
    def test_detect_and_handle_english_returns_translation(self, mock_get_client, _mock_ai):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "spanish_translation": "Fui a la tienda",
            "vocabulary_gaps": [
                {"english": "store", "spanish": "tienda"},
                {"english": "yesterday", "spanish": "ayer"},
            ],
            "encouragement": "¡Buen recuerdo!",
        })
        mock_client.chat.completions.create.return_value = mock_response

        engine = ConversationEngine()
        result = engine.detect_and_handle_english("I went to the store yesterday", "preterite", 2)

        assert result is not None
        assert result.spanish_translation == "Fui a la tienda"
        assert len(result.vocabulary_gaps) == 2
        assert result.vocabulary_gaps[0].english_word == "store"
        assert "En español" in result.display_message


class TestCorrectionSplitting:
    def test_explode_corrections_breaks_sentence_into_chunks(self):
        corr = Correction(
            original="si hay unos museos cerca el banco",
            corrected="sí hay unos museos cerca del banco",
            explanation="Fix accent and contraction",
            concept_id="articles",
        )
        exploded = _explode_corrections([corr])
        assert any(c.original == "si" and c.corrected == "sí" for c in exploded)
        assert any(c.original == "cerca el" and c.corrected == "cerca del" for c in exploded)


# ── Route integration ────────────────────────────────────────────────────────


class TestConversationRoutes:
    @pytest.fixture(autouse=True)
    def _setup_session(self):
        """Create a flow session for route tests."""
        ts = now_iso()
        with _open_connection() as conn:
            conn.execute(
                "INSERT INTO flow_sessions (started_at, flow_score, status) VALUES (?, 1000.0, 'active')",
                (ts,),
            )
            conn.commit()

    def test_start_conversation_creates_db_record(self):
        from fastapi.testclient import TestClient
        from spanish_vibes.app import app

        client = TestClient(app)
        resp = client.post(
            "/flow/conversation/start",
            data={"session_id": 1, "concept_id": "greetings", "topic": "deportes", "difficulty": 1},
        )
        assert resp.status_code == 200
        assert "Conversation" in resp.text or "conversation" in resp.text.lower()

        # Check DB record was created
        with _open_connection() as conn:
            row = conn.execute("SELECT * FROM flow_conversations WHERE session_id = 1").fetchone()
        assert row is not None
        assert row["topic"] == "deportes"
        assert row["concept_id"] == "greetings"

    def test_respond_adds_messages(self):
        from fastapi.testclient import TestClient
        from spanish_vibes.app import app

        client = TestClient(app)

        # Start a conversation first
        client.post(
            "/flow/conversation/start",
            data={"session_id": 1, "concept_id": "greetings", "topic": "comida", "difficulty": 1},
        )

        # Respond
        resp = client.post(
            "/flow/conversation/respond",
            data={"session_id": 1, "conversation_id": 1, "user_message": "¡Hola! Me gusta la comida."},
        )
        assert resp.status_code == 200

        # Check messages were updated once (AI opener + user + AI reply)
        with _open_connection() as conn:
            row = conn.execute("SELECT * FROM flow_conversations WHERE id = 1").fetchone()
        messages = json.loads(row["messages_json"])
        assert len(messages) == 3
        assert messages[0]["role"] == "ai"
        assert messages[1]["role"] == "user"
        assert messages[2]["role"] == "ai"

    def test_summary_returns_html(self):
        from fastapi.testclient import TestClient
        from spanish_vibes.app import app

        client = TestClient(app)

        # Start and do one exchange
        client.post(
            "/flow/conversation/start",
            data={"session_id": 1, "concept_id": "greetings", "topic": "música", "difficulty": 1},
        )

        resp = client.get(
            "/flow/conversation/summary",
            params={"conversation_id": 1, "session_id": 1},
        )
        assert resp.status_code == 200
        assert "Review" in resp.text or "Summary" in resp.text or "Continue" in resp.text


# ── Topic selection ─────────────────────────────────────────────────────────


class TestGetRandomTopic:
    def test_returns_topic_from_seeded_db(self):
        """When interest_topics has data, pick from it."""
        from spanish_vibes.db import seed_interest_topics
        seed_interest_topics()
        topic = get_random_topic()
        assert topic != ""
        assert topic != "la vida diaria"

    def test_returns_fallback_when_db_empty(self):
        """When interest_topics is empty, falls back to built-in list."""
        topic = get_random_topic()
        assert topic != ""
        assert topic != "la vida diaria"

    def test_excludes_specified_topic(self):
        """Should never return the excluded topic (given enough trials)."""
        from spanish_vibes.db import seed_interest_topics
        seed_interest_topics()
        results = {get_random_topic(exclude="Sports") for _ in range(30)}
        assert "Sports" not in results

    def test_fallback_openers_have_variety(self):
        """Each difficulty should have multiple openers."""
        engine = ConversationEngine()
        with patch("spanish_vibes.conversation.ai_available", return_value=False):
            openers = {engine.generate_opener("fútbol", "present_tense", 1) for _ in range(20)}
        assert len(openers) >= 3
