from __future__ import annotations

import re
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Literal

from fastapi import FastAPI, Form, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.responses import Response

from .db import (
    add_xp,
    count_due_cards,
    fetch_card_detail,
    fetch_decks,
    fetch_lesson_by_slug,
    fetch_lesson_deck_summaries,
    fetch_next_due_card,
    get_streak,
    get_xp,
    init_db,
    record_practice_today,
    update_card_schedule,
)
from .models import CardDetail, CardKind, CardDirection, DeckSummary, PlayerProgress
from .srs import GradingStrategy, SRS_FAST, calculate_xp_award, compare_answers, level_from_xp, person_label
from .flow_routes import router as flow_router
from .template_helpers import register_template_filters
from .web import router as lesson_router

PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_ROOT.parent.parent
TEMPLATES_DIR = PROJECT_ROOT / "templates"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
register_template_filters(templates.env)


def _chapter_label(slug: str) -> str:
    """Turn 'ch01-02-topic' into 'Ch 1.2'."""
    match = re.match(r"ch(\d+)-(\d+)", slug)
    if match:
        return f"Ch {int(match.group(1))}.{int(match.group(2))}"
    return ""


templates.env.filters["chapter_label"] = _chapter_label

# Ensure schema exists even if lifespan is bypassed (e.g. during tests).
init_db()


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    # Seed concept graph on startup
    from .concepts import seed_concepts_to_db, CONCEPTS_FILE
    if CONCEPTS_FILE.exists():
        seed_concepts_to_db()
        # On first run, convert existing cards to MCQ for tier-1 concepts (offline fallback)
        from .flow_ai import convert_existing_cards_to_mcq
        from .flow_db import count_cached_mcqs
        for concept_id in ["greetings", "numbers_1_20", "colors_basic"]:
            if count_cached_mcqs(concept_id) == 0:
                convert_existing_cards_to_mcq(concept_id)
    yield


app = FastAPI(title="Spanish Vibes", lifespan=lifespan)
app.include_router(lesson_router)
app.include_router(flow_router)


@dataclass(slots=True)
class QuizState:
    deck_ids: list[int]
    mode: CardKind
    direction: CardDirection
    grading: GradingStrategy


@dataclass(slots=True)
class QuizScore:
    points: int = 0
    streak: int = 0


DEFAULT_DIRECTION: CardDirection = "es_to_en"
DEFAULT_GRADING: GradingStrategy = "strict"
DEFAULT_MODE: CardKind = "vocab"


def _is_hx(request: Request) -> bool:
    return request.headers.get("HX-Request", "false").lower() == "true"


def _get_player_progress() -> PlayerProgress:
    import datetime as _dt

    xp = get_xp()
    level, xp_into, xp_needed = level_from_xp(xp)
    level_pct = int(xp_into / xp_needed * 100) if xp_needed > 0 else 100
    streak_count, streak_last = get_streak()
    today = _dt.date.today().isoformat()
    yesterday = (_dt.date.today() - _dt.timedelta(days=1)).isoformat()
    if streak_last not in (today, yesterday):
        streak_count = 0
    return PlayerProgress(
        xp=xp,
        level=level,
        xp_into_level=xp_into,
        xp_for_next_level=xp_needed,
        level_pct=level_pct,
        streak=streak_count,
        streak_last_date=streak_last,
    )


def _as_state(
    *,
    deck_ids: Iterable[int] | None,
    mode: str | None,
    direction: str | None,
    grading: str | None,
    available: dict[int, DeckSummary] | None = None,
) -> QuizState:
    available_decks = available or {deck.id: deck for deck in fetch_decks()}

    normalized_mode: CardKind = mode if mode in ("vocab", "fillblank", "verbs") else "vocab"
    normalized_direction: CardDirection = DEFAULT_DIRECTION
    if normalized_mode == "vocab" and direction == "en_to_es":
        normalized_direction = "en_to_es"
    elif normalized_mode == "fillblank":
        normalized_direction = "es_to_en"
    normalized_grading: GradingStrategy = "lenient" if grading == "lenient" else DEFAULT_GRADING

    filtered_ids: list[int]
    if deck_ids:
        filtered_ids = [deck_id for deck_id in deck_ids if deck_id in available_decks and available_decks[deck_id].kind == normalized_mode]
    else:
        filtered_ids = [deck_id for deck_id, deck in available_decks.items() if deck.kind == normalized_mode]

    if not filtered_ids:
        filtered_ids = [deck_id for deck_id, deck in available_decks.items() if deck.kind == normalized_mode]

    return QuizState(
        deck_ids=filtered_ids,
        mode=normalized_mode,
        direction=normalized_direction,
        grading=normalized_grading,
    )


def _default_state() -> QuizState:
    return _as_state(deck_ids=None, mode=DEFAULT_MODE, direction=DEFAULT_DIRECTION, grading=DEFAULT_GRADING)


def _score_from_values(points: int | None, streak: int | None) -> QuizScore:
    safe_points = max(0, points or 0)
    safe_streak = max(0, streak or 0)
    return QuizScore(points=safe_points, streak=safe_streak)


def _build_prompt(card: CardDetail, state: QuizState) -> dict[str, Any]:
    extra = card.extra or {}
    prompt: dict[str, Any] = {
        "mode_label": "Review",
        "lines": [],
        "answer_label": "Answer",
        "expected": card.solution,
        "example": None,
        "options": extra.get("options"),
        "input_type": "text",
        "placeholder": "Type your answer",
        "instructions": None,
    }

    if card.kind == "vocab":
        prompt["mode_label"] = "Vocabulary"
        spanish = extra.get("spanish")
        english = extra.get("english")
        example = extra.get("example") or extra.get("ex_es")

        if state.direction == "en_to_es":
            prompt_label = "English"
            prompt_value = english or card.prompt
            answer_label = "Spanish"
            expected = spanish or card.solution
        else:
            prompt_label = "Spanish"
            prompt_value = spanish or card.prompt
            answer_label = "English"
            expected = english or card.solution

        prompt["lines"].append({"label": prompt_label, "value": prompt_value})
        prompt["answer_label"] = answer_label
        prompt["expected"] = expected
        if example:
            prompt["example"] = example
        prompt["placeholder"] = "Type the translation"
        return prompt

    if card.kind == "fillblank":
        exercise = extra.get("exercise") if isinstance(extra.get("exercise"), dict) else None
        prompt["mode_label"] = "Fill in the Blank"
        if exercise:
            ex_prompt = exercise.get("prompt", card.prompt)
            prompt["lines"].append({"label": "Prompt", "value": ex_prompt})
            options = exercise.get("options")
            if options:
                prompt["options"] = options
                prompt["input_type"] = "options"
            instructions = exercise.get("instructions")
            if instructions:
                prompt["instructions"] = instructions
            prompt["answer_label"] = exercise.get("answer_label", "Answer")
            prompt["placeholder"] = "Type your answer"
        else:
            prompt["lines"].append({"label": "Sentence", "value": card.prompt})
            english = extra.get("english")
            if english:
                prompt["lines"].append({"label": "English", "value": english})
            prompt["answer_label"] = "Answer"
            prompt["placeholder"] = "Fill in the blank"
        reference = extra.get("reference")
        if reference:
            prompt["example"] = reference
        return prompt

    if card.kind == "verbs":
        prompt["mode_label"] = "Verb Conjugation"
        infinitive = extra.get("infinitive") or card.extra.get("spanish") or card.prompt
        tense = extra.get("tense") or ""
        person = extra.get("person") or extra.get("person_code")
        readable = person_label(person)
        person_display = f"{readable} ({person})" if readable and person else (person or "")
        prompt["lines"].extend(
            [
                {"label": "Infinitive", "value": infinitive},
                {"label": "Tense", "value": tense.title() if isinstance(tense, str) else tense},
                {"label": "Person", "value": person_display},
            ]
        )
        prompt["answer_label"] = "Conjugation"
        prompt["placeholder"] = "Type the conjugation"
        return prompt

    # Fallback for any other card type
    prompt["lines"].append({"label": "Prompt", "value": card.prompt})
    return prompt


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> Response:
    now = datetime.now(timezone.utc)
    deck_summaries = fetch_decks(now=now)
    deck_lookup = {deck.id: deck for deck in deck_summaries}
    state = _as_state(
        deck_ids=None,
        mode=DEFAULT_MODE,
        direction=DEFAULT_DIRECTION,
        grading=DEFAULT_GRADING,
        available=deck_lookup,
    )
    due_count = count_due_cards(now, deck_ids=state.deck_ids, kind=state.mode)

    # Build lesson_id → chapter label lookup for deck display
    lesson_summaries = fetch_lesson_deck_summaries(now)
    lesson_labels = {ls.id: _chapter_label(ls.slug) for ls in lesson_summaries}

    def _sort_key(deck: DeckSummary) -> tuple[int, int, str]:
        m = re.match(r"ch(\d+)-(\d+)", next((ls.slug for ls in lesson_summaries if ls.id == deck.lesson_id), ""))
        return (int(m.group(1)), int(m.group(2)), deck.name) if m else (999, 999, deck.name)

    deck_summaries.sort(key=_sort_key)

    vocab_decks = [deck for deck in deck_summaries if deck.kind == "vocab"]
    fillblank_decks = [deck for deck in deck_summaries if deck.kind == "fillblank"]
    verb_decks = [deck for deck in deck_summaries if deck.kind == "verbs"]

    # Concept mastery for hero section
    from .flow_routes import _count_mastered
    mastered, total = _count_mastered()

    context = {
        "page_title": "Spanish Vibes",
        "due_count": due_count,
        "state": state,
        "vocab_decks": vocab_decks,
        "fillblank_decks": fillblank_decks,
        "verb_decks": verb_decks,
        "lesson_labels": lesson_labels,
        "progress": _get_player_progress(),
        "concepts_mastered": mastered,
        "total_concepts": total,
        "current_page": "home",
    }
    return templates.TemplateResponse(request, "index.html", context)



@app.get("/quiz", response_class=HTMLResponse)
async def quiz_panel(
    request: Request,
    deck: list[int] = Query(None),
    mode: str | None = Query(None),
    direction: str | None = Query(None),
    grading: str | None = Query(None),
    points: int | None = Query(0),
    streak: int | None = Query(0),
    lesson: str | None = Query(None),
    kind: str | None = Query(None),
) -> Response:
    now = datetime.now(timezone.utc)

    # If lesson slug provided (from lessons page inline practice), resolve decks
    if lesson and not deck:
        lesson_info = fetch_lesson_by_slug(lesson)
        if lesson_info:
            all_decks = fetch_decks(now=now)
            lesson_decks = [d for d in all_decks if d.lesson_id == lesson_info.id]
            effective_kind = kind if kind in ("vocab", "fillblank", "verbs") else None
            if effective_kind:
                lesson_decks = [d for d in lesson_decks if d.kind == effective_kind] or lesson_decks
            deck = [d.id for d in lesson_decks]
            if not mode and lesson_decks:
                mode = effective_kind or lesson_decks[0].kind

    deck_summaries = fetch_decks()
    deck_lookup = {d.id: d for d in deck_summaries}
    state = _as_state(deck_ids=deck, mode=mode, direction=direction, grading=grading, available=deck_lookup)
    card = fetch_next_due_card(now, deck_ids=state.deck_ids, kind=state.mode)
    prompt = _build_prompt(card, state) if card else None
    score = _score_from_values(points, streak)
    context = {
        "card": card,
        "state": state,
        "prompt": prompt,
        "submitted_answer": "",
        "feedback": None,
        "score": score,
        "progress": _get_player_progress(),
    }
    return templates.TemplateResponse(request, "quiz.html", context)


@app.get("/practice", response_class=HTMLResponse)
async def practice(
    request: Request,
    lesson: str | None = Query(None),
    kind: str | None = Query(None),
    points: int | None = Query(0),
    streak: int | None = Query(0),
) -> Response:
    score = _score_from_values(points, streak)
    progress = _get_player_progress()

    if not lesson:
        state = _default_state()
        return templates.TemplateResponse(request, "practice.html", {
            "page_title": "Spanish Vibes · Practice",
            "card": None, "state": state, "prompt": None,
            "submitted_answer": "", "feedback": None,
            "score": score, "progress": progress,
            "lesson_info": None, "practice_kind": state.mode,
            "deck_kinds": [], "due_in_lesson": 0,
        })

    lesson_info = fetch_lesson_by_slug(lesson)
    if lesson_info is None:
        state = _default_state()
        return templates.TemplateResponse(request, "practice.html", {
            "page_title": "Spanish Vibes · Practice",
            "card": None, "state": state, "prompt": None,
            "submitted_answer": "", "feedback": None,
            "score": score, "progress": progress,
            "lesson_info": None, "practice_kind": state.mode,
            "deck_kinds": [], "due_in_lesson": 0,
        })

    now = datetime.now(timezone.utc)
    all_lesson_decks = fetch_decks(now=now)
    all_lesson_decks = [d for d in all_lesson_decks if d.lesson_id == lesson_info.id]
    deck_kinds = sorted({d.kind for d in all_lesson_decks})

    lesson_decks = [d for d in all_lesson_decks if d.kind == kind] if kind in ("vocab", "fillblank", "verbs") else all_lesson_decks
    if not lesson_decks:
        lesson_decks = all_lesson_decks

    deck_lookup = {d.id: d for d in lesson_decks}
    effective_kind = kind if kind in ("vocab", "fillblank", "verbs") else None
    state = _as_state(
        deck_ids=[d.id for d in lesson_decks],
        mode=effective_kind or (lesson_decks[0].kind if lesson_decks else DEFAULT_MODE),
        direction=DEFAULT_DIRECTION,
        grading=DEFAULT_GRADING,
        available=deck_lookup,
    )

    card = fetch_next_due_card(now, deck_ids=state.deck_ids, kind=state.mode)
    prompt = _build_prompt(card, state) if card else None
    due_in_lesson = sum(d.due_count for d in all_lesson_decks)

    ch_label = _chapter_label(lesson_info.slug)
    title_prefix = f"{ch_label} " if ch_label else ""

    context = {
        "page_title": f"Spanish Vibes · Practice {title_prefix}{lesson_info.title}",
        "card": card,
        "state": state,
        "prompt": prompt,
        "submitted_answer": "",
        "feedback": None,
        "score": score,
        "progress": progress,
        "lesson_info": lesson_info,
        "practice_kind": state.mode,
        "deck_kinds": deck_kinds,
        "due_in_lesson": due_in_lesson,
    }
    return templates.TemplateResponse(request, "practice.html", context)


@app.get("/decks", response_class=HTMLResponse)
async def decks_page(request: Request) -> Response:
    summaries = fetch_lesson_deck_summaries(datetime.now(timezone.utc))

    def _ch_key(s: Any) -> tuple[int, int]:
        m = re.match(r"ch(\d+)-(\d+)", s.slug)
        return (int(m.group(1)), int(m.group(2))) if m else (999, 999)

    summaries.sort(key=_ch_key)
    total_lessons = len(summaries)
    total_decks = sum(len(lesson.decks) for lesson in summaries)
    total_cards = sum(lesson.total_cards for lesson in summaries)
    total_due = sum(lesson.due_cards for lesson in summaries)

    context = {
        "page_title": "Spanish Vibes · Decks",
        "lessons": summaries,
        "totals": {
            "lessons": total_lessons,
            "decks": total_decks,
            "cards": total_cards,
            "due": total_due,
        },
        "progress": _get_player_progress(),
        "current_page": "decks",
    }
    return templates.TemplateResponse(request, "decks.html", context)


@app.post("/check/{card_id}", response_class=HTMLResponse)
async def check_card(
    request: Request,
    card_id: int,
    answer: str = Form(""),
    deck: list[int] = Form(None),
    mode: str | None = Form(None),
    direction: str | None = Form(None),
    grading: str | None = Form(None),
    points: int = Form(0),
    streak: int = Form(0),
) -> Response:
    deck_summaries = fetch_decks()
    deck_lookup = {d.id: d for d in deck_summaries}
    state = _as_state(deck_ids=deck, mode=mode, direction=direction, grading=grading, available=deck_lookup)
    score = _score_from_values(points, streak)
    card = fetch_card_detail(card_id)
    if card is None or card.kind != state.mode or card.deck_id not in state.deck_ids:
        context = {
            "card": None,
            "state": state,
            "prompt": None,
            "submitted_answer": "",
            "feedback": None,
            "score": score,
            "progress": _get_player_progress(),
        }
        return templates.TemplateResponse(request, "quiz.html", context)

    prompt = _build_prompt(card, state)
    expected = prompt.get("expected", "")
    provided_raw = answer.strip()
    is_correct = compare_answers(expected, provided_raw, state.grading)
    now = datetime.now(timezone.utc)
    verdict: Literal["good", "again"] = "good" if is_correct else "again"
    update_card_schedule(card, verdict, now, fast_mode=SRS_FAST)

    updated_score = QuizScore(
        points=score.points + (1 if is_correct else 0),
        streak=(score.streak + 1) if is_correct else 0,
    )

    xp_earned = 0
    if is_correct:
        xp_earned = calculate_xp_award(score.streak)
        add_xp(xp_earned)
        record_practice_today(now.strftime("%Y-%m-%d"))

    feedback_message = "Correct! +1 point." if is_correct else "Keep practicing."
    feedback = {
        "is_correct": is_correct,
        "expected": expected,
        "provided": provided_raw,
        "label": prompt["answer_label"],
        "message": feedback_message,
        "xp_earned": xp_earned,
    }

    next_card = fetch_next_due_card(now, deck_ids=state.deck_ids, kind=state.mode)
    next_prompt = _build_prompt(next_card, state) if next_card else None

    context = {
        "card": next_card,
        "state": state,
        "prompt": next_prompt,
        "submitted_answer": "",
        "feedback": feedback,
        "score": updated_score,
        "progress": _get_player_progress(),
    }
    return templates.TemplateResponse(request, "quiz.html", context)


def main() -> None:
    import uvicorn

    uvicorn.run("spanish_vibes.app:app", host="127.0.0.1", port=8000, reload=True)


if __name__ == "__main__":
    main()
