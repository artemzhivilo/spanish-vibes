"""FastAPI routes for Flow Mode v2 — concept-based MCQ learning."""

from __future__ import annotations

import json
from pathlib import Path

import markdown

from fastapi import APIRouter, BackgroundTasks, Form, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.responses import Response

from .flow import (
    FlowCardContext,
    build_session_state,
    end_flow_session,
    process_mcq_answer,
    select_next_card,
    start_or_resume_session,
)
from .flow_ai import ai_available, ensure_cache_populated, prefetch_next_concepts
from .flow_db import get_session, mark_teach_shown, get_all_concept_knowledge
from .concepts import load_concepts
from .bkt import is_mastered

router = APIRouter()

PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_ROOT.parent.parent
TEMPLATES_DIR = PROJECT_ROOT / "templates"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _count_mastered() -> tuple[int, int]:
    """Return (mastered_count, total_count)."""
    concepts = load_concepts()
    knowledge = get_all_concept_knowledge()
    mastered = sum(
        1 for cid, ck in knowledge.items()
        if cid in concepts and is_mastered(ck.p_mastery, ck.n_attempts)
    )
    return mastered, len(concepts)


@router.get("/flow", response_class=HTMLResponse)
async def flow_page(request: Request) -> Response:
    """Full-screen Flow Mode page."""
    from .app import _get_player_progress
    session = start_or_resume_session()
    state = build_session_state(session.id)
    progress = _get_player_progress()
    mastered, total = _count_mastered()
    context = {
        "page_title": "Spanish Vibes · Flow",
        "session": session,
        "streak": state.current_streak if state else 0,
        "cards_answered": session.cards_answered,
        "correct_count": session.correct_count,
        "progress": progress,
        "concepts_mastered": mastered,
        "total_concepts": total,
        "current_page": "flow",
    }
    return templates.TemplateResponse(request, "flow.html", context)


@router.get("/flow/card", response_class=HTMLResponse)
async def flow_card(
    request: Request,
    session_id: int = Query(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
) -> Response:
    """Return the next card partial for HTMX swap."""
    card_context = select_next_card(session_id)

    if card_context is None:
        return templates.TemplateResponse(request, "partials/flow_complete.html", {
            "session": get_session(session_id),
            "message": "No cards available. Import lessons or check back later!",
        })

    # Background prefetch for upcoming concepts
    background_tasks.add_task(prefetch_next_concepts)

    if card_context.card_type == "teach":
        context = {
            "session_id": session_id,
            "card_context": card_context,
            "concept_name": _get_concept_name(card_context.concept_id),
            "teach_html": _render_teach(card_context.teach_content),
        }
        return templates.TemplateResponse(request, "partials/flow_card.html", context)

    # MCQ card
    context = {
        "session_id": session_id,
        "card_context": card_context,
        "concept_name": _get_concept_name(card_context.concept_id),
        "card_json": json.dumps({
            "card_type": card_context.card_type,
            "concept_id": card_context.concept_id,
            "question": card_context.question,
            "correct_answer": card_context.correct_answer,
            "options": card_context.options,
            "option_misconceptions": card_context.option_misconceptions,
            "difficulty": card_context.difficulty,
            "mcq_card_id": card_context.mcq_card_id,
        }),
    }
    return templates.TemplateResponse(request, "partials/flow_card.html", context)


@router.post("/flow/answer", response_class=HTMLResponse)
async def flow_answer(
    request: Request,
    session_id: int = Form(...),
    chosen_option: str = Form(""),
    card_json: str = Form("{}"),
    start_time: int = Form(0),
    background_tasks: BackgroundTasks = BackgroundTasks(),
) -> Response:
    """Process MCQ tap and return feedback partial."""
    import time

    card_data = json.loads(card_json)
    now_ms = int(time.time() * 1000)
    response_time_ms = (now_ms - start_time) if start_time > 0 else None

    card_context = FlowCardContext(
        card_type=card_data.get("card_type", "mcq"),
        concept_id=card_data.get("concept_id", ""),
        question=card_data.get("question", ""),
        correct_answer=card_data.get("correct_answer", ""),
        options=card_data.get("options", []),
        option_misconceptions=card_data.get("option_misconceptions", {}),
        difficulty=int(card_data.get("difficulty", 1)),
        mcq_card_id=card_data.get("mcq_card_id"),
    )

    result = process_mcq_answer(
        session_id=session_id,
        card_context=card_context,
        chosen_option=chosen_option,
        response_time_ms=response_time_ms,
    )

    # Prefetch in background
    background_tasks.add_task(prefetch_next_concepts)

    context = {
        "session_id": session_id,
        "result": result,
        "chosen_option": chosen_option,
        "correct_answer": result.correct_answer,
        "is_correct": result.is_correct,
        "xp_earned": result.xp_earned,
        "streak": result.streak,
        "cards_answered": result.cards_answered,
        "concepts_mastered": result.concepts_mastered,
        "total_concepts": result.total_concepts,
        "concept_name": _get_concept_name(result.concept_id),
        "misconception_hint": _get_misconception_hint(result.misconception_concept),
    }
    return templates.TemplateResponse(request, "partials/flow_feedback.html", context)


@router.post("/flow/teach-seen", response_class=HTMLResponse)
async def flow_teach_seen(
    request: Request,
    session_id: int = Form(...),
    concept_id: str = Form(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
) -> Response:
    """Mark teach card seen, ensure MCQs exist, return first MCQ."""
    mark_teach_shown(concept_id)

    # Ensure MCQ cache is populated for this concept
    background_tasks.add_task(ensure_cache_populated, concept_id)

    # Return next card (will be an MCQ now)
    card_context = select_next_card(session_id)
    if card_context is None:
        return templates.TemplateResponse(request, "partials/flow_complete.html", {
            "session": get_session(session_id),
            "message": "Generating practice questions... Refresh to continue!",
        })

    if card_context.card_type == "teach":
        context = {
            "session_id": session_id,
            "card_context": card_context,
            "concept_name": _get_concept_name(card_context.concept_id),
            "teach_html": _render_teach(card_context.teach_content),
        }
        return templates.TemplateResponse(request, "partials/flow_card.html", context)

    context = {
        "session_id": session_id,
        "card_context": card_context,
        "concept_name": _get_concept_name(card_context.concept_id),
        "card_json": json.dumps({
            "card_type": card_context.card_type,
            "concept_id": card_context.concept_id,
            "question": card_context.question,
            "correct_answer": card_context.correct_answer,
            "options": card_context.options,
            "option_misconceptions": card_context.option_misconceptions,
            "difficulty": card_context.difficulty,
            "mcq_card_id": card_context.mcq_card_id,
        }),
    }
    return templates.TemplateResponse(request, "partials/flow_card.html", context)


@router.post("/flow/end", response_class=HTMLResponse)
async def flow_end(
    request: Request,
    session_id: int = Form(...),
) -> Response:
    """End session and show summary."""
    session = end_flow_session(session_id)
    if session is None:
        session = get_session(session_id)

    from .app import _get_player_progress

    accuracy = 0
    if session and session.cards_answered > 0:
        accuracy = int(session.correct_count / session.cards_answered * 100)

    mastered, total = _count_mastered()

    context = {
        "session": session,
        "accuracy": accuracy,
        "progress": _get_player_progress(),
        "concepts_mastered": mastered,
        "total_concepts": total,
    }
    return templates.TemplateResponse(request, "partials/flow_complete.html", context)


@router.post("/flow/skip-to-tier", response_class=HTMLResponse)
async def flow_skip_to_tier(
    request: Request,
    tier: int = Form(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
) -> Response:
    """Mark all concepts below a given tier as mastered, so the user starts at that tier."""
    from .flow_db import update_concept_knowledge, mark_teach_shown as _mark_teach

    concepts = load_concepts()
    for concept_id, concept in concepts.items():
        if concept.difficulty_level < tier:
            # Mark as mastered: p_mastery=0.95, 10 fake attempts all correct
            _mark_teach(concept_id)
            update_concept_knowledge(concept_id, 0.95, True)
            # Set enough attempts to pass the is_mastered threshold
            from .db import _open_connection
            with _open_connection() as conn:
                conn.execute(
                    "UPDATE concept_knowledge SET n_attempts = 10, n_correct = 10 WHERE concept_id = ?",
                    (concept_id,),
                )

    # Populate MCQ cache for new tier concepts
    for concept_id, concept in concepts.items():
        if concept.difficulty_level == tier:
            background_tasks.add_task(ensure_cache_populated, concept_id)

    # End current session so a fresh one starts
    from .flow_db import get_active_session, end_session
    active = get_active_session()
    if active:
        end_session(active.id)

    # Redirect to flow page
    from starlette.responses import RedirectResponse
    return RedirectResponse(url="/flow", status_code=303)


@router.get("/flow/concepts", response_class=HTMLResponse)
async def concepts_page(request: Request) -> Response:
    """Visual curriculum map showing all concepts grouped by tier."""
    from .app import _get_player_progress

    concepts = load_concepts()
    knowledge = get_all_concept_knowledge()
    progress = _get_player_progress()

    # Build status for each concept
    concept_list = []
    for concept_id, concept in concepts.items():
        ck = knowledge.get(concept_id)
        n_attempts = ck.n_attempts if ck else 0
        n_correct = ck.n_correct if ck else 0
        p_mastery = ck.p_mastery if ck else 0.0
        mastery_pct = int(p_mastery * 100)
        accuracy = int(n_correct / n_attempts * 100) if n_attempts > 0 else 0

        from .concepts import prerequisites_met
        prereqs_met = prerequisites_met(concept_id, knowledge, concepts)

        if is_mastered(p_mastery, n_attempts):
            status = "mastered"
        elif n_attempts > 0:
            status = "learning"
        elif prereqs_met:
            status = "new"
        else:
            status = "locked"

        concept_list.append({
            "id": concept_id,
            "name": concept.name,
            "description": concept.description,
            "tier": concept.difficulty_level,
            "status": status,
            "mastery_pct": mastery_pct,
            "n_attempts": n_attempts,
            "n_correct": n_correct,
            "accuracy": accuracy,
            "teach_preview": (concept.teach_content or "")[:120],
        })

    # Group by tier
    tiers: dict[int, list] = {}
    for c in concept_list:
        tiers.setdefault(c["tier"], []).append(c)

    mastered_count = sum(1 for c in concept_list if c["status"] == "mastered")

    context = {
        "page_title": "Spanish Vibes · Concepts",
        "tiers": dict(sorted(tiers.items())),
        "total_concepts": len(concept_list),
        "mastered_count": mastered_count,
        "progress": progress,
        "current_page": "concepts",
    }
    return templates.TemplateResponse(request, "concepts.html", context)


@router.get("/flow/stats", response_class=HTMLResponse)
async def stats_page(request: Request) -> Response:
    """Study statistics and session history."""
    from .app import _get_player_progress
    from .flow_db import get_recent_sessions

    concepts = load_concepts()
    knowledge = get_all_concept_knowledge()
    progress = _get_player_progress()
    sessions = get_recent_sessions(limit=10)

    # Aggregates
    total_sessions = len(sessions)
    total_cards = sum(s.cards_answered for s in sessions)
    total_correct = sum(s.correct_count for s in sessions)
    overall_accuracy = int(total_correct / total_cards * 100) if total_cards > 0 else 0

    # Per-concept stats
    concept_stats = []
    mastered_count = 0
    for concept_id, concept in concepts.items():
        ck = knowledge.get(concept_id)
        n_attempts = ck.n_attempts if ck else 0
        n_correct = ck.n_correct if ck else 0
        p_mastery = ck.p_mastery if ck else 0.0
        mastery_pct = int(p_mastery * 100)
        accuracy = int(n_correct / n_attempts * 100) if n_attempts > 0 else 0
        mastered = is_mastered(p_mastery, n_attempts)
        if mastered:
            mastered_count += 1

        concept_stats.append({
            "name": concept.name,
            "tier": concept.difficulty_level,
            "n_attempts": n_attempts,
            "accuracy": accuracy,
            "mastery_pct": mastery_pct,
            "status": "mastered" if mastered else ("learning" if n_attempts > 0 else "new"),
        })

    concept_stats.sort(key=lambda c: (c["tier"], c["name"]))

    # Session history with accuracy
    session_rows = []
    for s in sessions:
        acc = int(s.correct_count / s.cards_answered * 100) if s.cards_answered > 0 else 0
        session_rows.append({
            "date": s.started_at[:16].replace("T", " "),
            "cards": s.cards_answered,
            "accuracy": acc,
            "xp": s.xp_earned,
            "streak": s.longest_streak,
            "status": s.status,
        })

    context = {
        "page_title": "Spanish Vibes · Stats",
        "total_sessions": total_sessions,
        "total_cards": total_cards,
        "overall_accuracy": overall_accuracy,
        "mastered_count": mastered_count,
        "total_concepts": len(concepts),
        "concept_stats": concept_stats,
        "sessions": session_rows,
        "progress": progress,
        "current_page": "stats",
    }
    return templates.TemplateResponse(request, "flow_stats.html", context)


def _render_teach(content: str | None) -> str:
    """Convert markdown teach_content to HTML."""
    if not content:
        return ""
    return markdown.markdown(content.strip())


def _get_concept_name(concept_id: str) -> str:
    concepts = load_concepts()
    concept = concepts.get(concept_id)
    return concept.name if concept else concept_id


def _get_misconception_hint(misconception_id: str | None) -> str:
    if not misconception_id:
        return ""
    concepts = load_concepts()
    concept = concepts.get(misconception_id)
    if concept:
        return f"Review: {concept.name}"
    return ""
