"""Tests for trending content sourcing module."""

from __future__ import annotations

import json
import time
from unittest.mock import patch

import pytest

from spanish_vibes.content_source import (
    CACHE_TTL_SECONDS,
    TopicSummary,
    TrendingTopics,
    refresh_trending_cache,
)


class TestExtractKeywords:
    def test_extracts_words(self):
        kw = TrendingTopics.extract_keywords("Real Madrid gana la Champions League")
        assert "real" in kw
        assert "madrid" in kw
        assert "gana" in kw
        assert "champions" in kw
        assert "league" in kw

    def test_filters_stop_words(self):
        kw = TrendingTopics.extract_keywords("El gato en la casa de los niños")
        assert "gato" in kw
        assert "casa" in kw
        assert "niños" in kw
        # Stop words should be filtered
        assert "los" not in kw
        assert "del" not in kw

    def test_empty_string(self):
        kw = TrendingTopics.extract_keywords("")
        assert kw == []

    def test_short_words_filtered(self):
        kw = TrendingTopics.extract_keywords("a el no si")
        assert kw == []


class TestMapToInterests:
    def test_matches_by_name(self):
        topic = TopicSummary(
            title="Football World Cup finals",
            summary="",
            keywords=["football", "world", "cup"],
        )
        interests = [
            {"name": "Football", "slug": "football"},
            {"name": "Music", "slug": "music"},
        ]
        matched = TrendingTopics.map_to_interests(topic, interests)
        assert len(matched) == 1
        assert matched[0]["slug"] == "football"

    def test_matches_by_slug_with_hyphen(self):
        topic = TopicSummary(
            title="New food cooking show",
            summary="",
            keywords=["food", "cooking", "show"],
        )
        interests = [
            {"name": "Food & Cooking", "slug": "food-cooking"},
            {"name": "Sports", "slug": "sports"},
        ]
        matched = TrendingTopics.map_to_interests(topic, interests)
        assert len(matched) == 1
        assert matched[0]["slug"] == "food-cooking"

    def test_no_match(self):
        topic = TopicSummary(
            title="Quantum physics breakthrough",
            summary="",
            keywords=["quantum", "physics"],
        )
        interests = [
            {"name": "Football", "slug": "football"},
            {"name": "Music", "slug": "music"},
        ]
        matched = TrendingTopics.map_to_interests(topic, interests)
        assert matched == []


class TestFetchTrending:
    @patch("spanish_vibes.content_source._feedparser")
    def test_parses_rss_entries(self, mock_feedparser):
        mock_feedparser.parse.return_value = {
            "entries": [
                {
                    "title": "Breaking: Football match today",
                    "summary": "A summary",
                    "link": "https://example.com/1",
                    "published": "2026-02-13",
                },
                {
                    "title": "Music festival in Madrid",
                    "summary": "Festival info",
                    "link": "https://example.com/2",
                    "published": "2026-02-13",
                },
            ]
        }

        fetcher = TrendingTopics()
        topics = fetcher.fetch_trending(language="es", count=10)
        assert len(topics) == 2
        assert topics[0].title == "Breaking: Football match today"
        assert topics[1].source_url == "https://example.com/2"
        assert len(topics[0].keywords) > 0

    @patch("spanish_vibes.content_source._feedparser")
    def test_respects_count_limit(self, mock_feedparser):
        mock_feedparser.parse.return_value = {
            "entries": [{"title": f"Item {i}", "summary": "", "link": "", "published": ""} for i in range(20)]
        }
        fetcher = TrendingTopics()
        topics = fetcher.fetch_trending(count=5)
        assert len(topics) == 5

    @patch("spanish_vibes.content_source._feedparser", None)
    def test_returns_empty_without_feedparser(self):
        fetcher = TrendingTopics()
        topics = fetcher.fetch_trending()
        assert topics == []


class TestCacheTTL:
    def test_uses_cache_when_fresh(self, tmp_path):
        import spanish_vibes.content_source as cs
        original_cache = cs.CACHE_FILE
        cs.CACHE_FILE = tmp_path / "trending_cache.json"

        cache_data = {
            "cached_at": time.time(),
            "topics": [
                {
                    "title": "Cached topic",
                    "summary": "From cache",
                    "keywords": ["cached"],
                    "source_url": "",
                    "published_date": "",
                    "language": "es",
                }
            ],
        }
        cs.CACHE_FILE.write_text(json.dumps(cache_data))

        topics = refresh_trending_cache()
        assert len(topics) == 1
        assert topics[0].title == "Cached topic"

        cs.CACHE_FILE = original_cache

    def test_refreshes_stale_cache(self, tmp_path):
        import spanish_vibes.content_source as cs
        original_cache = cs.CACHE_FILE
        cs.CACHE_FILE = tmp_path / "trending_cache.json"

        cache_data = {
            "cached_at": time.time() - CACHE_TTL_SECONDS - 100,
            "topics": [
                {
                    "title": "Stale topic",
                    "summary": "",
                    "keywords": [],
                    "source_url": "",
                    "published_date": "",
                    "language": "es",
                }
            ],
        }
        cs.CACHE_FILE.write_text(json.dumps(cache_data))

        with patch.object(TrendingTopics, "fetch_trending", return_value=[
            TopicSummary(title="Fresh topic", summary="New", keywords=["fresh"]),
        ]):
            with patch("spanish_vibes.db.get_all_interest_topics", return_value=[]):
                topics = refresh_trending_cache()

        assert len(topics) == 1
        assert topics[0].title == "Fresh topic"

        cs.CACHE_FILE = original_cache
