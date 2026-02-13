from __future__ import annotations

import re
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from . import lessons
from .db import fetch_all_lesson_slugs, fetch_lesson_deck_summaries, fetch_lesson_mastery, get_lesson_by_slug, upsert_lesson_with_content
from .importer import parse_lesson_markdown

router = APIRouter()

PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_ROOT.parent.parent
TEMPLATES_DIR = PROJECT_ROOT / "templates"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _chapter_label(slug: str) -> str:
    """Turn 'ch01-02-topic' into 'Ch 1.2'."""
    m = re.match(r"ch(\d+)-(\d+)", slug)
    return f"Ch {int(m.group(1))}.{int(m.group(2))}" if m else ""


templates.env.filters["chapter_label"] = _chapter_label


def _chapter_sort_key(slug: str) -> tuple[int, int]:
    m = re.match(r"ch(\d+)-(\d+)", slug)
    return (int(m.group(1)), int(m.group(2))) if m else (999, 999)


def _mastery_tier(mastery: dict[str, int]) -> str:
    total = mastery.get("total", 0)
    if total == 0:
        return "none"
    mastered = mastery.get("mastered", 0)
    pct = mastered / total * 100
    if pct >= 90:
        return "gold"
    if pct >= 60:
        return "silver"
    if pct >= 25:
        return "bronze"
    return "none"


@router.get("/lessons", response_class=HTMLResponse)
async def lessons_index(request: Request) -> HTMLResponse:
    from .app import _get_player_progress

    summaries = fetch_lesson_deck_summaries(datetime.now(timezone.utc))
    summaries.sort(key=lambda s: _chapter_sort_key(s.slug))

    total_lessons = len(summaries)
    total_cards = sum(s.total_cards for s in summaries)
    total_due = sum(s.due_cards for s in summaries)

    mastery_raw = fetch_lesson_mastery()
    mastery: dict[int, dict[str, Any]] = {}
    for lesson_id, data in mastery_raw.items():
        tier = _mastery_tier(data)
        mastery[lesson_id] = {**data, "tier": tier}

    # Group by chapter number
    chapters: OrderedDict[int, list] = OrderedDict()
    for s in summaries:
        ch, _ = _chapter_sort_key(s.slug)
        chapters.setdefault(ch, []).append(s)

    context = {
        "page_title": "Spanish Vibes · Lessons",
        "chapters": chapters,
        "totals": {
            "lessons": total_lessons,
            "cards": total_cards,
            "due": total_due,
            "chapters": len(chapters),
        },
        "mastery": mastery,
        "progress": _get_player_progress(),
        "current_page": "lessons",
    }
    return templates.TemplateResponse(request, "lessons.html", context)


@router.get("/lesson/{slug}", response_class=HTMLResponse)
async def lesson_page(request: Request, slug: str) -> HTMLResponse:
    from .app import _get_player_progress

    lesson_row = get_lesson_by_slug(slug)
    if lesson_row is None:
        raise HTTPException(status_code=404, detail="Lesson not found")

    ch_label = _chapter_label(lesson_row["slug"])
    title_prefix = f"{ch_label} " if ch_label else ""

    # Compute prev/next lesson for navigation
    all_slugs = fetch_all_lesson_slugs()
    all_slugs.sort(key=_chapter_sort_key)
    prev_slug = None
    next_slug = None
    try:
        idx = all_slugs.index(slug)
        if idx > 0:
            prev_slug = all_slugs[idx - 1]
        if idx < len(all_slugs) - 1:
            next_slug = all_slugs[idx + 1]
    except ValueError:
        pass

    context = {
        "page_title": f"Spanish Vibes · {title_prefix}{lesson_row['title']}",
        "lesson": lesson_row,
        "content_html": lesson_row.get("content_html", ""),
        "progress": _get_player_progress(),
        "prev_slug": prev_slug,
        "next_slug": next_slug,
    }
    return templates.TemplateResponse(request, "lesson.html", context)


@router.post("/lesson/{slug}/refresh", response_class=HTMLResponse)
async def refresh_lesson(request: Request, slug: str) -> RedirectResponse:
    lesson_row = get_lesson_by_slug(slug)
    if lesson_row is None:
        raise HTTPException(status_code=404, detail="Lesson not found")

    path_value = lesson_row.get("path") or ""
    if not path_value:
        raise HTTPException(status_code=400, detail="Lesson path is not set")

    lesson_path = Path(path_value)
    if not lesson_path.exists():
        raise HTTPException(status_code=404, detail="Lesson file is missing on disk")

    parsed, content_sha, rendered_html = parse_lesson_markdown(lesson_path)
    status, lesson_id = upsert_lesson_with_content(
        slug=parsed.doc.slug,
        title=parsed.doc.title,
        level_score=parsed.doc.level_score,
        difficulty=parsed.doc.difficulty,
        path=lesson_path.as_posix(),
        content_sha=content_sha,
        content_html=rendered_html,
    )
    lessons.sync_lesson(parsed, lesson_id=lesson_id)

    return RedirectResponse(url=f"/lesson/{slug}", status_code=303)
