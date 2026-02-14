"""Trending content sourcing — fetches trending topics and maps them to interests."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import feedparser as _feedparser
except ImportError:
    _feedparser = None  # type: ignore[assignment]

PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_ROOT.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
CACHE_FILE = DATA_DIR / "trending_cache.json"
CACHE_TTL_SECONDS = 24 * 60 * 60  # 24 hours


@dataclass(slots=True)
class TopicSummary:
    """A trending topic from an external source."""

    title: str
    summary: str
    keywords: list[str] = field(default_factory=list)
    source_url: str = ""
    published_date: str = ""
    language: str = "es"


class TrendingTopics:
    """Fetches and processes trending topics from news RSS feeds."""

    def fetch_trending(self, language: str = "es", count: int = 10) -> list[TopicSummary]:
        """Parse Google News RSS for trending topics."""
        if _feedparser is None:
            return []

        geo = "ES" if language == "es" else "US"
        url = f"https://news.google.com/rss?hl={language}&gl={geo}&ceid={geo}:{language}"

        try:
            feed = _feedparser.parse(url)
        except Exception:
            return []

        topics: list[TopicSummary] = []
        for entry in feed.get("entries", [])[:count]:
            title = entry.get("title", "")
            summary = entry.get("summary", "")
            link = entry.get("link", "")
            published = entry.get("published", "")

            keywords = self.extract_keywords(title)

            topics.append(TopicSummary(
                title=title,
                summary=summary,
                keywords=keywords,
                source_url=link,
                published_date=published,
                language=language,
            ))

        return topics

    @staticmethod
    def extract_keywords(text: str) -> list[str]:
        """Extract keywords using simple word extraction (no NLP)."""
        # Remove common stop words and short words
        stop_words = {
            "the", "a", "an", "is", "are", "was", "were", "in", "on", "at",
            "to", "for", "of", "and", "or", "but", "not", "with", "by", "from",
            "el", "la", "los", "las", "un", "una", "de", "del", "en", "con",
            "por", "para", "que", "es", "son", "y", "o", "no", "se", "su",
        }
        # Extract words (letters only, 3+ chars)
        words = re.findall(r"\b[a-záéíóúñü]{3,}\b", text.lower())
        return [w for w in words if w not in stop_words]

    @staticmethod
    def map_to_interests(
        topic: TopicSummary,
        interests: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Match a trending topic to interest categories by keyword overlap."""
        keywords_lower = {k.lower() for k in topic.keywords}
        title_lower = topic.title.lower()

        matched: list[dict[str, Any]] = []
        for interest in interests:
            slug = interest.get("slug", "")
            name = interest.get("name", "").lower()

            # Check if interest name or slug appears in title or keywords
            if (
                name in title_lower
                or slug.replace("-", " ") in title_lower
                or any(name in kw or kw in name for kw in keywords_lower)
            ):
                matched.append(interest)

        return matched


def refresh_trending_cache() -> list[TopicSummary]:
    """Fetch trending topics and cache with 24h TTL."""
    # Check TTL
    if CACHE_FILE.exists():
        try:
            cache = json.loads(CACHE_FILE.read_text())
            cached_at = cache.get("cached_at", 0)
            if time.time() - cached_at < CACHE_TTL_SECONDS:
                return [
                    TopicSummary(**t) for t in cache.get("topics", [])
                ]
        except (json.JSONDecodeError, TypeError, KeyError):
            pass

    # Fetch fresh data
    fetcher = TrendingTopics()
    topics = fetcher.fetch_trending(language="es", count=10)

    # Map to interests
    from .db import get_all_interest_topics
    interests = get_all_interest_topics()
    for topic in topics:
        matched = fetcher.map_to_interests(topic, interests)
        # Store matched interest slugs in keywords for later use
        for m in matched:
            slug = m.get("slug", "")
            if slug and slug not in topic.keywords:
                topic.keywords.append(slug)

    # Write cache
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    cache_data = {
        "cached_at": time.time(),
        "topics": [
            {
                "title": t.title,
                "summary": t.summary,
                "keywords": t.keywords,
                "source_url": t.source_url,
                "published_date": t.published_date,
                "language": t.language,
            }
            for t in topics
        ],
    }
    CACHE_FILE.write_text(json.dumps(cache_data, ensure_ascii=False, indent=2))
    return topics


__all__ = [
    "TopicSummary",
    "TrendingTopics",
    "refresh_trending_cache",
]
