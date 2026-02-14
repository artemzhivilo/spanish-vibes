"""Tests for topic-themed AI generation in flow_ai.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from spanish_vibes import db
from spanish_vibes.db import init_db
from spanish_vibes.flow_ai import (
    _mcq_hash,
    ensure_cache_populated,
    generate_conversation_opener,
    generate_mcq_batch,
    generate_teach_card,
)


@pytest.fixture(autouse=True)
def _setup_db(tmp_path):
    db.DB_PATH = tmp_path / "test.db"
    init_db()
    # Seed a concept for testing
    from spanish_vibes.db import _open_connection, now_iso
    ts = now_iso()
    with _open_connection() as conn:
        conn.execute(
            "INSERT INTO concepts (id, name, description, difficulty_level, teach_content, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("greetings", "Greetings", "Basic greetings", 1, "Learn how to say hello.", ts),
        )
        conn.commit()


class TestMcqHashIncludesTopic:
    """Cache key should differ based on topic."""

    def test_hash_differs_with_topic(self):
        h1 = _mcq_hash("greetings", "What is hello?", "hola")
        h2 = _mcq_hash("greetings", "What is hello?", "hola", "sports")
        assert h1 != h2

    def test_hash_same_without_topic(self):
        h1 = _mcq_hash("greetings", "What is hello?", "hola")
        h2 = _mcq_hash("greetings", "What is hello?", "hola", None)
        assert h1 == h2

    def test_different_topics_different_hashes(self):
        h1 = _mcq_hash("greetings", "Q?", "A", "sports")
        h2 = _mcq_hash("greetings", "Q?", "A", "music")
        assert h1 != h2


class TestThemedMcqBatch:
    """generate_mcq_batch should include topic in the prompt."""

    @patch("spanish_vibes.flow_ai.ai_available", return_value=True)
    @patch("spanish_vibes.flow_ai._get_client")
    def test_topic_appears_in_prompt(self, mock_get_client, _mock_ai):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        # Mock the response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '[]'
        mock_client.chat.completions.create.return_value = mock_response

        generate_mcq_batch("greetings", count=5, topic="football")

        # Verify the API was called
        call_args = mock_client.chat.completions.create.call_args
        messages = call_args.kwargs.get("messages") or call_args[1].get("messages")
        system_msg = messages[0]["content"]
        assert "football" in system_msg

    @patch("spanish_vibes.flow_ai.ai_available", return_value=True)
    @patch("spanish_vibes.flow_ai._get_client")
    def test_no_topic_no_theming(self, mock_get_client, _mock_ai):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '[]'
        mock_client.chat.completions.create.return_value = mock_response

        generate_mcq_batch("greetings", count=5, topic=None)

        call_args = mock_client.chat.completions.create.call_args
        messages = call_args.kwargs.get("messages") or call_args[1].get("messages")
        system_msg = messages[0]["content"]
        assert "Theme the content around" not in system_msg


class TestEnsureCachePopulatedFallback:
    """ensure_cache_populated should fall back when themed generation fails."""

    @patch("spanish_vibes.flow_ai.ai_available", return_value=True)
    @patch("spanish_vibes.flow_ai.generate_mcq_batch")
    @patch("spanish_vibes.flow_ai.count_cached_mcqs", return_value=0)
    def test_fallback_on_empty_themed_result(self, _mock_count, mock_gen, _mock_ai):
        # First call with topic returns empty, second without topic returns results
        mock_gen.side_effect = [[], [1, 2, 3]]

        result = ensure_cache_populated("greetings", topic="football")
        assert result == 3
        assert mock_gen.call_count == 2
        # First call with topic, second without
        assert mock_gen.call_args_list[0].kwargs.get("topic") == "football"
        assert "topic" not in mock_gen.call_args_list[1].kwargs


class TestGenerateTeachCard:
    """generate_teach_card should use static content when no topic/no AI."""

    def test_returns_static_without_topic(self):
        content = generate_teach_card("greetings")
        # Should return the static teach content from loaded concepts
        assert len(content) > 0

    @patch("spanish_vibes.flow_ai.ai_available", return_value=False)
    def test_returns_static_without_ai(self, _mock_ai):
        content = generate_teach_card("greetings", topic="sports")
        # Without AI, should fall back to static
        assert len(content) > 0

    def test_returns_empty_for_unknown_concept(self):
        content = generate_teach_card("nonexistent_xyz_concept")
        assert content == ""


class TestGenerateConversationOpener:
    """generate_conversation_opener should return empty without AI."""

    @patch("spanish_vibes.flow_ai.ai_available", return_value=False)
    def test_returns_empty_without_ai(self, _mock_ai):
        result = generate_conversation_opener("greetings", "sports")
        assert result == ""

    @patch("spanish_vibes.flow_ai.ai_available", return_value=True)
    @patch("spanish_vibes.flow_ai._get_client")
    def test_returns_opener_with_ai(self, mock_get_client, _mock_ai):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "¡Hola! ¿Te gusta el fútbol?"
        mock_client.chat.completions.create.return_value = mock_response

        result = generate_conversation_opener("greetings", "football", difficulty=1)
        assert "fútbol" in result
