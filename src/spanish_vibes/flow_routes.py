"""FastAPI routes for Flow Mode v2 — concept-based MCQ learning."""

from __future__ import annotations

import json
from html import escape
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import asdict
import re
from typing import Any

import markdown

from fastapi import APIRouter, BackgroundTasks, Form, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.responses import Response, RedirectResponse

from .flow import (
    FlowCardContext,
    build_session_state,
    end_flow_session,
    get_user_level,
    process_mcq_answer,
    select_next_card,
    start_or_resume_session,
)
from .flow_ai import ensure_cache_populated, generate_story_card, prefetch_next_concepts
from .interest import CardSignal, InterestTracker, get_topic_id_for_conversation
from .interest import seed_interest_scores
from .flow_db import (
    clear_mcq_cache,
    get_session,
    mark_teach_shown,
    get_all_concept_knowledge,
    store_vocabulary_gap,
    update_session,
    get_last_conversation_info,
    get_concept_knowledge,
    update_concept_knowledge,
)
from .db import (
    _open_connection,
    consume_dev_override,
    delete_dev_override,
    get_all_dev_overrides,
    get_current_user_id,
    get_all_interest_topics,
    is_user_onboarded,
    now_iso,
    seed_interest_topics,
    set_user_onboarded,
    set_dev_override,
)
from .concepts import load_concepts, prerequisites_met
from .bkt import is_mastered, bkt_update
from .lexicon import translate_spanish_word
from .personas import (
    get_persona_prompt,
    load_all_personas,
    load_persona,
    select_persona,
)
from .conversation_types import get_type_instruction, select_conversation_type
from .evaluation import (
    apply_placement_results,
    compute_enjoyment_score,
    evaluate_conversation,
    update_persona_engagement,
)
from .template_helpers import register_template_filters
from .words import (
    mark_word_introduced,
    mark_word_practice_result,
    record_word_tap,
)
from .memory import (
    get_persona_memories,
    get_user_profile,
    store_persona_memories,
    store_user_facts,
)
from . import prompts as prompt_config

router = APIRouter()

PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_ROOT.parent.parent
TEMPLATES_DIR = PROJECT_ROOT / "templates"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
register_template_filters(templates.env)


def _count_mastered() -> tuple[int, int]:
    """Return (mastered_count, total_count)."""
    concepts = load_concepts()
    knowledge = get_all_concept_knowledge()
    mastered = sum(
        1
        for cid, ck in knowledge.items()
        if cid in concepts and is_mastered(ck.p_mastery, ck.n_attempts)
    )
    return mastered, len(concepts)


def _uid() -> int:
    return get_current_user_id()


@router.get("/flow", response_class=HTMLResponse)
async def flow_page(request: Request, dev: str | None = Query(None)) -> Response:
    """Full-screen Flow Mode page.  Add ?dev=1 to show dev tools."""
    if not is_user_onboarded():
        return RedirectResponse(url="/flow/onboarding", status_code=303)

    show_dev = dev == "1"

    from .app import _get_player_progress

    session = start_or_resume_session()
    state = build_session_state(session.id)
    progress = _get_player_progress()
    mastered, total = _count_mastered()
    concepts = load_concepts()
    knowledge = get_all_concept_knowledge()
    user_level_info = get_user_level(knowledge, concepts)
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
        "user_cefr": user_level_info["cefr"],
        "user_level": user_level_info["level"],
        "tier_mastery": user_level_info["tier_mastery"],
        "show_dev": show_dev,
    }
    if show_dev:
        personas = load_all_personas()
        overrides = get_all_dev_overrides()
        context.update(
            {
                "dev_personas": personas,
                "dev_concepts": sorted(
                    concepts.values(), key=lambda c: (c.difficulty_level, c.name)
                ),
                "dev_overrides": overrides,
            }
        )
    return templates.TemplateResponse(request, "flow.html", context)


@router.get("/flow/onboarding", response_class=HTMLResponse)
async def onboarding_page(request: Request) -> Response:
    """Render onboarding questions before placement conversation."""
    if is_user_onboarded():
        return RedirectResponse(url="/flow", status_code=303)
    topics = get_all_interest_topics()
    concepts = load_concepts()
    tiers: dict[int, list[dict[str, str]]] = {}
    for concept_id, concept in sorted(
        concepts.items(), key=lambda item: (item[1].difficulty_level, item[1].name)
    ):
        tiers.setdefault(concept.difficulty_level, []).append(
            {
                "id": concept_id,
                "name": concept.name,
            }
        )
    context = {
        "page_title": "Spanish Vibes · Onboarding",
        "topics": topics,
        "tier_catalog": [
            {"tier": tier, "concepts": entries}
            for tier, entries in sorted(tiers.items())
        ],
    }
    return templates.TemplateResponse(request, "flow_onboarding.html", context)


@router.post("/flow/onboarding/start-placement", response_class=HTMLResponse)
async def start_placement(
    request: Request,
    start_tier: int = Form(1),
    start_concept_id: str = Form(""),
    interest_topic_ids: list[int] = Form(default=[]),
) -> Response:
    """Apply onboarding start selection and jump into flow directly."""
    if is_user_onboarded():
        return RedirectResponse(url="/flow", status_code=303)

    if interest_topic_ids:
        try:
            seed_interest_scores(interest_topic_ids, initial_score=0.35)
        except Exception:
            pass

    concepts = load_concepts()
    if not concepts:
        set_user_onboarded(True)
        return RedirectResponse(url="/flow", status_code=303)

    max_tier = max(c.difficulty_level for c in concepts.values())
    tier = max(1, min(max_tier, int(start_tier)))

    for concept_id, concept in concepts.items():
        if concept.difficulty_level < tier:
            mark_teach_shown(concept_id)
            update_concept_knowledge(concept_id, 0.95, True)
            with _open_connection() as conn:
                conn.execute(
                    "UPDATE concept_knowledge SET n_attempts = 10, n_correct = 10 WHERE user_id = ? AND concept_id = ?",
                    (_uid(), concept_id),
                )

    selected_concept_id = start_concept_id.strip()
    if selected_concept_id in concepts and concepts[selected_concept_id].difficulty_level == tier:
        set_dev_override("force_next_concept", selected_concept_id)
    else:
        tier_concepts = sorted(
            [
                cid
                for cid, concept in concepts.items()
                if concept.difficulty_level == tier
            ],
            key=lambda cid: concepts[cid].name,
        )
        if tier_concepts:
            set_dev_override("force_next_concept", tier_concepts[0])

    from .flow_db import get_active_session, end_session

    active = get_active_session()
    if active:
        end_session(active.id)

    set_user_onboarded(True)
    return RedirectResponse(url="/flow", status_code=303)


@router.get("/flow/onboarding/results", response_class=HTMLResponse)
async def placement_results(
    request: Request,
    conversation_id: int = Query(...),
    session_id: int = Query(...),
) -> Response:
    """Compatibility route: placement results are rendered via summary."""
    return RedirectResponse(
        url=f"/flow/conversation/summary?conversation_id={conversation_id}&session_id={session_id}",
        status_code=303,
    )


@router.get("/flow/card", response_class=HTMLResponse)
async def flow_card(
    request: Request,
    session_id: int = Query(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
) -> Response:
    """Return the next card partial for HTMX swap."""
    card_context = select_next_card(session_id)

    if card_context is None:
        return templates.TemplateResponse(
            request,
            "partials/flow_complete.html",
            {
                "session": get_session(session_id),
                "message": "No cards available. Import lessons or check back later!",
            },
        )

    # Background prefetch for upcoming concepts
    background_tasks.add_task(prefetch_next_concepts)

    if card_context.card_type == "teach":
        context = {
            "session_id": session_id,
            "card_context": card_context,
            "concept_name": _get_concept_name(card_context.concept_id),
            "teach_html": _render_teach(card_context.teach_content),
            "persona_id": "",
            "conversation_type": card_context.conversation_type,
        }
        return templates.TemplateResponse(request, "partials/flow_card.html", context)

    if card_context.card_type in {"conversation", "story_comprehension"}:
        from .conversation import get_random_topic

        topic = (
            card_context.interest_topics[0]
            if card_context.interest_topics
            else get_random_topic()
        )
        conversation_type = card_context.conversation_type or (
            "story_comprehension"
            if card_context.card_type == "story_comprehension"
            else "general_chat"
        )
        target_concept_id = card_context.target_concept_id or card_context.concept_id

        if card_context.card_type == "story_comprehension":
            return _render_story_comprehension_card(
                request=request,
                session_id=session_id,
                concept_id=target_concept_id,
                topic=topic,
                difficulty=card_context.difficulty,
                conversation_type=conversation_type,
            )

        return _start_chat_conversation_card(
            request=request,
            session_id=session_id,
            concept_id=target_concept_id,
            topic=topic,
            difficulty=card_context.difficulty,
            conversation_type=conversation_type,
        )

    if card_context.card_type == "word_intro":
        context = {
            "session_id": session_id,
            "card_context": card_context,
            "concept_name": _get_concept_name(card_context.concept_id),
            "persona_id": "",
            "conversation_type": card_context.conversation_type,
        }
        return templates.TemplateResponse(request, "partials/flow_card.html", context)

    if card_context.card_type == "word_practice":
        concept_teach_html = _get_concept_teach_html(card_context.concept_id)
        context = {
            "session_id": session_id,
            "card_context": card_context,
            "concept_name": _get_concept_name(card_context.concept_id),
            "concept_teach_html": concept_teach_html,
            "persona_id": "",
            "conversation_type": card_context.conversation_type,
            "card_json": json.dumps(
                {
                    "card_type": card_context.card_type,
                    "concept_id": card_context.concept_id,
                    "question": card_context.question,
                    "correct_answer": card_context.correct_answer,
                    "options": card_context.options,
                    "option_misconceptions": card_context.option_misconceptions,
                    "difficulty": card_context.difficulty,
                    "mcq_card_id": card_context.mcq_card_id,
                    "word_id": card_context.word_id,
                    "word_spanish": card_context.word_spanish,
                }
            ),
        }
        return templates.TemplateResponse(request, "partials/flow_card.html", context)

    if card_context.card_type in {
        "sentence_builder",
        "emoji_association",
        "fill_blank",
    }:
        concept_teach_html = _get_concept_teach_html(card_context.concept_id)
        context = {
            "session_id": session_id,
            "card_context": card_context,
            "concept_name": _get_concept_name(card_context.concept_id),
            "concept_teach_html": concept_teach_html,
            "persona_id": "",
            "conversation_type": card_context.conversation_type,
            "card_json": json.dumps(
                {
                    "card_type": card_context.card_type,
                    "concept_id": card_context.concept_id,
                    "question": card_context.question,
                    "correct_answer": card_context.correct_answer,
                    "options": card_context.options,
                    "option_misconceptions": card_context.option_misconceptions,
                    "difficulty": card_context.difficulty,
                    "mcq_card_id": card_context.mcq_card_id,
                    "word_id": card_context.word_id,
                    "word_spanish": card_context.word_spanish,
                    "word_emoji": card_context.word_emoji,
                    "word_english": card_context.word_english,
                    "word_sentence": card_context.word_sentence,
                    "scrambled_words": card_context.scrambled_words,
                    "correct_sentence": card_context.correct_sentence,
                    "english_prompt": card_context.english_prompt,
                }
            ),
        }
        return templates.TemplateResponse(request, "partials/flow_card.html", context)

    if card_context.card_type == "word_match":
        concept_teach_html = _get_concept_teach_html(card_context.concept_id)
        context = {
            "session_id": session_id,
            "card_context": card_context,
            "concept_name": _get_concept_name(card_context.concept_id),
            "concept_teach_html": concept_teach_html,
            "persona_id": "",
            "conversation_type": card_context.conversation_type,
        }
        return templates.TemplateResponse(request, "partials/flow_card.html", context)

    # MCQ card
    concept_teach_html = _get_concept_teach_html(card_context.concept_id)
    context = {
        "session_id": session_id,
        "card_context": card_context,
        "concept_name": _get_concept_name(card_context.concept_id),
        "concept_teach_html": concept_teach_html,
        "persona_id": "",
        "conversation_type": card_context.conversation_type,
        "card_json": json.dumps(
            {
                "card_type": card_context.card_type,
                "concept_id": card_context.concept_id,
                "question": card_context.question,
                "correct_answer": card_context.correct_answer,
                "options": card_context.options,
                "option_misconceptions": card_context.option_misconceptions,
                "difficulty": card_context.difficulty,
                "mcq_card_id": card_context.mcq_card_id,
                "english_prompt": card_context.english_prompt,
            }
        ),
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
        word_id=card_data.get("word_id"),
        word_spanish=card_data.get("word_spanish", ""),
        word_emoji=card_data.get("word_emoji"),
        word_english=card_data.get("word_english", ""),
        word_sentence=card_data.get("word_sentence", ""),
        scrambled_words=card_data.get("scrambled_words", []),
        correct_sentence=card_data.get("correct_sentence", ""),
        english_prompt=card_data.get("english_prompt", ""),
    )

    result = process_mcq_answer(
        session_id=session_id,
        card_context=card_context,
        chosen_option=chosen_option,
        response_time_ms=response_time_ms,
    )

    if (
        card_context.card_type in {"word_practice", "emoji_association"}
        and card_context.word_id
    ):
        mark_word_practice_result(card_context.word_id, result.is_correct)

    # Record interest signal (topic_id=None until cards are topic-tagged)
    signal = CardSignal(
        topic_id=None,
        was_correct=result.is_correct,
        dwell_time_ms=response_time_ms,
        response_time_ms=response_time_ms,
        card_id=card_context.mcq_card_id,
        session_id=session_id,
        concept_id=card_context.concept_id,
        card_type=card_context.card_type,
    )
    InterestTracker().update_from_card_signal(signal)

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
        "wrong_explanation": (
            _build_wrong_explanation(
                card_type=card_context.card_type,
                chosen_option=chosen_option,
                correct_answer=result.correct_answer,
                misconception_hint=_get_misconception_hint(result.misconception_concept),
            )
            if not result.is_correct
            else ""
        ),
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
        return templates.TemplateResponse(
            request,
            "partials/flow_complete.html",
            {
                "session": get_session(session_id),
                "message": "Generating practice questions... Refresh to continue!",
            },
        )

    if card_context.card_type == "teach":
        context = {
            "session_id": session_id,
            "card_context": card_context,
            "concept_name": _get_concept_name(card_context.concept_id),
            "teach_html": _render_teach(card_context.teach_content),
            "persona_id": "",
            "conversation_type": card_context.conversation_type,
        }
        return templates.TemplateResponse(request, "partials/flow_card.html", context)

    context = {
        "session_id": session_id,
        "card_context": card_context,
        "concept_name": _get_concept_name(card_context.concept_id),
        "persona_id": "",
        "conversation_type": card_context.conversation_type,
        "card_json": json.dumps(
            {
                "card_type": card_context.card_type,
                "concept_id": card_context.concept_id,
                "question": card_context.question,
                "correct_answer": card_context.correct_answer,
                "options": card_context.options,
                "option_misconceptions": card_context.option_misconceptions,
                "difficulty": card_context.difficulty,
                "mcq_card_id": card_context.mcq_card_id,
                "english_prompt": card_context.english_prompt,
            }
        ),
    }
    return templates.TemplateResponse(request, "partials/flow_card.html", context)


@router.post("/flow/word-intro/complete", response_class=HTMLResponse)
async def flow_word_intro_complete(
    request: Request,
    session_id: int = Form(...),
    word_id: int = Form(...),
) -> Response:
    mark_word_introduced(word_id)
    return await flow_card(request, session_id=session_id)


@router.post("/flow/word-match/submit", response_class=HTMLResponse)
async def flow_word_match_submit(
    request: Request,
) -> Response:
    form_data = await request.form()
    try:
        session_id = int(str(form_data.get("session_id") or "0"))
        count = int(str(form_data.get("pair_count") or "0"))
    except ValueError:
        return HTMLResponse("<p>Invalid match submission.</p>", status_code=400)

    if session_id <= 0 or count <= 0:
        return HTMLResponse("<p>Invalid match submission.</p>", status_code=400)

    concept_id = str(form_data.get("concept_id") or "greetings").strip() or "greetings"
    correct_pairs = 0
    for idx in range(count):
        word_id = form_data.get(f"word_id_{idx}")
        expected = form_data.get(f"answer_key_{idx}")
        answer = form_data.get(f"answer_{idx}")
        is_pair_correct = bool(expected and answer == expected)
        if is_pair_correct:
            correct_pairs += 1
        if word_id and expected:
            mark_word_practice_result(int(word_id), is_pair_correct)

    all_correct = correct_pairs == count
    result = process_mcq_answer(
        session_id=session_id,
        card_context=FlowCardContext(
            card_type="word_match",
            concept_id=concept_id,
            question="Match the pairs",
            correct_answer="All pairs matched",
            difficulty=1,
        ),
        chosen_option="All pairs matched" if all_correct else f"{correct_pairs}/{count} pairs",
        response_time_ms=None,
    )

    context = {
        "session_id": session_id,
        "result": result,
        "chosen_option": "" if all_correct else f"{correct_pairs}/{count} pairs",
        "correct_answer": result.correct_answer,
        "is_correct": result.is_correct,
        "xp_earned": result.xp_earned,
        "streak": result.streak,
        "cards_answered": result.cards_answered,
        "concepts_mastered": result.concepts_mastered,
        "total_concepts": result.total_concepts,
        "concept_name": _get_concept_name(result.concept_id),
        "misconception_hint": None,
        "wrong_explanation": (
            f"You matched {correct_pairs}/{count} pairs. "
            "Each Spanish item must be linked to its exact English translation."
            if not all_correct
            else ""
        ),
    }
    return templates.TemplateResponse(request, "partials/flow_feedback.html", context)


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
                    "UPDATE concept_knowledge SET n_attempts = 10, n_correct = 10 WHERE user_id = ? AND concept_id = ?",
                    (_uid(), concept_id),
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
    set_user_onboarded(True)

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

        concept_list.append(
            {
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
            }
        )

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

        concept_stats.append(
            {
                "name": concept.name,
                "tier": concept.difficulty_level,
                "n_attempts": n_attempts,
                "accuracy": accuracy,
                "mastery_pct": mastery_pct,
                "status": "mastered"
                if mastered
                else ("learning" if n_attempts > 0 else "new"),
            }
        )

    concept_stats.sort(key=lambda c: (c["tier"], c["name"]))

    # Session history with accuracy
    session_rows = []
    for s in sessions:
        acc = (
            int(s.correct_count / s.cards_answered * 100) if s.cards_answered > 0 else 0
        )
        session_rows.append(
            {
                "date": s.started_at[:16].replace("T", " "),
                "cards": s.cards_answered,
                "accuracy": acc,
                "xp": s.xp_earned,
                "streak": s.longest_streak,
                "status": s.status,
            }
        )

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


@router.get("/flow/interests", response_class=HTMLResponse)
async def interests_dashboard(request: Request) -> Response:
    """Developer dashboard exposing interest-topic internals."""
    from .db import _open_connection

    tracker = InterestTracker()
    seed_interest_topics()
    top_topics = tracker.get_top_interests(n=25)
    now = datetime.now(timezone.utc)

    with _open_connection() as conn:
        user_id = _uid()
        topic_rows = conn.execute(
            """
            SELECT t.id, t.name, t.slug, t.parent_id,
                   s.score, s.interaction_count, s.last_updated, s.decay_half_life_days
            FROM interest_topics t
            LEFT JOIN user_interest_scores s ON s.topic_id = t.id AND s.user_id = ?
            ORDER BY COALESCE(s.score, 0) DESC, t.name
            """,
            (user_id,),
        ).fetchall()
        total_signals_row = conn.execute(
            "SELECT COUNT(*) AS c FROM card_signals WHERE user_id = ?", (user_id,)
        ).fetchone()
        signal_rows = conn.execute(
            """
            SELECT cs.id, cs.topic_id, cs.was_correct, cs.dwell_time_ms,
                   cs.response_time_ms, cs.was_skipped, cs.concept_id, cs.card_type,
                   cs.created_at, t.name AS topic_name
            FROM card_signals cs
            LEFT JOIN interest_topics t ON t.id = cs.topic_id
            WHERE cs.user_id = ?
            ORDER BY cs.id DESC
            LIMIT 25
            """,
            (user_id,),
        ).fetchall()

    topics: list[dict[str, Any]] = []
    decayed_values: list[float] = []
    for row in topic_rows:
        raw_score = row["score"]
        last_updated = row["last_updated"]
        half_life = row["decay_half_life_days"] or 45.0
        decayed = None
        if raw_score is not None and last_updated:
            decayed = InterestTracker._apply_decay(  # type: ignore[attr-defined]
                score=float(raw_score),
                last_updated=str(last_updated),
                half_life_days=float(half_life),
                now=now,
            )
            decayed_values.append(decayed)
        topics.append(
            {
                "id": int(row["id"]),
                "name": row["name"],
                "slug": row["slug"],
                "parent_id": row["parent_id"],
                "score": raw_score,
                "decayed": decayed,
                "interaction_count": row["interaction_count"] or 0,
                "last_updated": last_updated,
            }
        )

    total_signals = int(total_signals_row["c"] if total_signals_row else 0)
    recent_signals = [
        {
            "id": row["id"],
            "topic": row["topic_name"] or "(none)",
            "topic_id": row["topic_id"],
            "created_at": row["created_at"],
            "card_type": row["card_type"],
            "was_correct": bool(row["was_correct"]),
            "dwell_time_ms": row["dwell_time_ms"],
            "was_skipped": bool(row["was_skipped"]),
            "concept_id": row["concept_id"],
        }
        for row in signal_rows
    ]

    avg_decayed = sum(decayed_values) / len(decayed_values) if decayed_values else 0.0
    tracked_topics = sum(1 for t in topics if t["score"] is not None)
    last_signal_at = recent_signals[0]["created_at"] if recent_signals else None

    context = {
        "page_title": "Spanish Vibes · Interests",
        "current_page": "flow",
        "top_topics": top_topics,
        "topics": topics,
        "recent_signals": recent_signals,
        "total_topics": len(topics),
        "tracked_topics": tracked_topics,
        "avg_decayed": avg_decayed,
        "total_signals": total_signals,
        "last_signal_at": last_signal_at,
    }
    return templates.TemplateResponse(request, "flow_interests.html", context)


@router.get("/flow/words", response_class=HTMLResponse)
async def words_dashboard(request: Request) -> Response:
    """Developer dashboard for the vocabulary lifecycle."""
    from .db import _open_connection

    with _open_connection() as conn:
        status_rows = conn.execute(
            "SELECT status, COUNT(*) AS c FROM words GROUP BY status",
        ).fetchall()
        total_words_row = conn.execute("SELECT COUNT(*) AS c FROM words").fetchone()
        recent_rows = conn.execute(
            """
            SELECT w.*, c.name AS concept_name
            FROM words w
            LEFT JOIN concepts c ON c.id = w.concept_id
            ORDER BY w.updated_at DESC
            LIMIT 50
            """,
        ).fetchall()
        practicing_rows = conn.execute(
            """
            SELECT w.*, c.name AS concept_name
            FROM words w
            LEFT JOIN concepts c ON c.id = w.concept_id
            WHERE w.status IN ('introduced', 'practicing')
            ORDER BY w.updated_at ASC
            LIMIT 25
            """,
        ).fetchall()

    status_totals = {str(row["status"]): int(row["c"]) for row in status_rows}
    total_words = int(total_words_row["c"] if total_words_row else 0)

    context = {
        "page_title": "Spanish Vibes · Words",
        "current_page": "flow",
        "status_totals": status_totals,
        "total_words": total_words,
        "recent_words": [dict(row) for row in recent_rows],
        "practice_words": [dict(row) for row in practicing_rows],
    }
    return templates.TemplateResponse(request, "flow_words.html", context)


# ── Conversation card routes ─────────────────────────────────────────────────


@router.get("/flow/translate-word", response_class=HTMLResponse)
async def translate_word_endpoint(
    request: Request,
    word: str = Query(...),
    context: str = Query(""),
    conversation_id: int | None = Query(default=None),
) -> Response:
    """Return a lightweight tooltip with a Spanish→English translation.

    Also records the tap so the system knows which words the user is looking up.
    """

    try:
        result = translate_spanish_word(word, context)
    except Exception:
        result = None
    english = result["translation"] if result else None
    spanish_clean = result["word"] if result else word

    # Record that the user tapped this word
    try:
        record_word_tap(
            spanish=spanish_clean,
            english=english,
            conversation_id=conversation_id,
            source="conversation" if conversation_id else "general",
        )
    except Exception:
        pass

    if result is None:
        body = '<div class="text-slate-400">(translation unavailable)</div>'
    else:
        word_html = escape(result["word"])
        translation_html = escape(result["translation"])
        body = (
            '<div class="flex flex-col gap-1">'
            f'<div><span class="font-bold text-emerald-300">{word_html}</span>'
            '<span class="text-slate-500 mx-1">→</span>'
            f'<span class="text-slate-100">{translation_html}</span></div>'
            "</div>"
        )
    return HTMLResponse(body)


@router.post("/flow/conversation/start", response_class=HTMLResponse)
async def conversation_start(
    request: Request,
    session_id: int = Form(...),
    concept_id: str = Form(""),
    topic: str = Form(""),
    difficulty: int = Form(1),
    conversation_type: str = Form(""),
) -> Response:
    """Start a conversation card and return the chat UI."""

    # Pick concept/topic from flow context if not provided
    if not concept_id:
        card_context = select_next_card(session_id)
        concept_id = card_context.concept_id if card_context else "greetings"
        if card_context and card_context.card_type == "story_comprehension":
            return _render_story_comprehension_card(
                request=request,
                session_id=session_id,
                concept_id=concept_id,
                topic=topic or "",
                difficulty=card_context.difficulty,
                conversation_type=card_context.conversation_type
                or "story_comprehension",
            )
        if card_context and card_context.interest_topics:
            import random

            topic = topic or random.choice(card_context.interest_topics)
    if not topic:
        from .conversation import get_random_topic

        topic = get_random_topic()
    forced_type = consume_dev_override("force_next_conversation_type")
    selected_type, target_concept_id = (
        (conversation_type, concept_id)
        if conversation_type
        else (
            (forced_type, concept_id)
            if forced_type
            else select_conversation_type(concept_id, session_id)
        )
    )
    effective_concept_id = target_concept_id or concept_id

    if selected_type == "story_comprehension":
        return _render_story_comprehension_card(
            request=request,
            session_id=session_id,
            concept_id=effective_concept_id,
            topic=topic,
            difficulty=difficulty,
            conversation_type=selected_type,
        )

    return _start_chat_conversation_card(
        request=request,
        session_id=session_id,
        concept_id=effective_concept_id,
        topic=topic,
        difficulty=difficulty,
        conversation_type=selected_type,
    )


@router.post("/flow/story-card/start", response_class=HTMLResponse)
async def story_card_start(
    request: Request,
    session_id: int = Form(...),
    concept_id: str = Form(""),
    topic: str = Form(""),
    difficulty: int = Form(1),
) -> Response:
    from .conversation import get_random_topic

    if not concept_id:
        card_context = select_next_card(session_id)
        concept_id = card_context.concept_id if card_context else "greetings"
        if card_context and card_context.interest_topics:
            import random

            topic = topic or random.choice(card_context.interest_topics)
    if not topic:
        topic = get_random_topic()

    return _render_story_comprehension_card(
        request=request,
        session_id=session_id,
        concept_id=concept_id,
        topic=topic,
        difficulty=difficulty,
        conversation_type="story_comprehension",
    )


@router.post("/flow/story-card/submit", response_class=HTMLResponse)
async def story_card_submit(
    request: Request,
    session_id: int = Form(...),
    concept_id: str = Form(...),
    story_payload_json: str = Form("{}"),
) -> Response:
    payload = json.loads(story_payload_json or "{}")
    story_text = str(payload.get("story") or "")
    questions = payload.get("questions") or []
    if not isinstance(questions, list) or not questions:
        return HTMLResponse("<p>Story questions missing.</p>", status_code=400)

    form = await request.form()
    total = 0
    correct = 0
    for idx, question in enumerate(questions):
        if not isinstance(question, dict):
            continue
        expected = str(question.get("correct_answer") or "").strip()
        if not expected:
            continue
        chosen = str(form.get(f"answer_{idx}") or "").strip()
        total += 1
        if chosen == expected:
            correct += 1

    if total <= 0:
        return HTMLResponse("<p>No valid questions answered.</p>", status_code=400)

    # A story card is graded as a single card event, with pass at >=60% correct.
    pass_score = correct / total >= 0.6
    result = process_mcq_answer(
        session_id=session_id,
        card_context=FlowCardContext(
            card_type="story_comprehension",
            concept_id=concept_id,
            question=f"Story comprehension ({correct}/{total})",
            correct_answer="pass",
            difficulty=2,
        ),
        chosen_option="pass" if pass_score else "fail",
        response_time_ms=None,
        count_card=False,
    )

    try:
        from .words import harvest_conversation_words

        if story_text:
            harvest_conversation_words([story_text], concept_id=concept_id or None)
    except Exception:
        pass

    context = {
        "session_id": session_id,
        "result": result,
        "chosen_option": f"{correct}/{total}",
        "correct_answer": f"{correct}/{total} correct",
        "is_correct": result.is_correct,
        "xp_earned": result.xp_earned,
        "streak": result.streak,
        "cards_answered": result.cards_answered,
        "concepts_mastered": result.concepts_mastered,
        "total_concepts": result.total_concepts,
        "concept_name": _get_concept_name(result.concept_id),
        "misconception_hint": None,
        "wrong_explanation": (
            f"You got {correct}/{total}. A passing score is at least 60%."
            if not result.is_correct
            else ""
        ),
    }
    return templates.TemplateResponse(request, "partials/flow_feedback.html", context)


@router.post("/flow/conversation/respond", response_class=HTMLResponse)
async def conversation_respond(
    request: Request,
    session_id: int = Form(...),
    conversation_id: int = Form(...),
    user_message: str = Form(""),
) -> Response:
    """User sends a message — single LLM call evaluates, replies, and steers."""
    from .conversation import (
        ConversationCard,
        ConversationEngine,
        ConversationMessage,
    )
    from .db import _open_connection, now_iso

    engine = ConversationEngine()
    timestamp = now_iso()

    # Load conversation from DB
    with _open_connection() as conn:
        user_id = _uid()
        row = conn.execute(
            "SELECT * FROM flow_conversations WHERE user_id = ? AND id = ?",
            (user_id, conversation_id),
        ).fetchone()

    if row is None:
        return HTMLResponse("<p>Conversation not found.</p>", status_code=404)

    topic = str(row["topic"])
    concept_id = str(row["concept_id"] or "")
    difficulty = int(row["difficulty"])
    conversation_type = str(row["conversation_type"] or "general_chat")
    persona = load_persona(row["persona_id"])
    type_instruction = get_type_instruction(
        conversation_type,
        concept_id=concept_id,
        topic=topic,
        persona_id=persona.id,
        starting_level=difficulty if conversation_type == "placement" else None,
    )
    persona_prompt = _compose_persona_prompt(persona, type_instruction=type_instruction)
    existing_messages = json.loads(row["messages_json"])
    messages = [ConversationMessage.from_dict(m) for m in existing_messages]

    clean_message = user_message.strip()
    english_result = engine.detect_and_handle_english(
        clean_message,
        concept_id,
        difficulty,
    )

    user_text_for_engine = (
        english_result.spanish_translation if english_result else clean_message
    )

    # Single LLM call: evaluate + reply + steer
    conversation_guardrails = _build_conversation_guardrails(
        concept_id=concept_id,
        difficulty=difficulty,
    )
    result = engine.respond_to_user(
        messages=messages,
        user_text=user_text_for_engine,
        topic=topic,
        concept=concept_id,
        difficulty=difficulty,
        persona_prompt=persona_prompt,
        persona_name=persona.name,
        conversation_guardrails=conversation_guardrails,
    )

    # Add user message with corrections from the evaluation
    corrections = (
        None if english_result else (result.corrections if result.corrections else None)
    )
    user_msg = ConversationMessage(
        role="user",
        content=clean_message,
        corrections=corrections,
        timestamp=timestamp,
    )
    messages.append(user_msg)

    if english_result:
        system_msg = ConversationMessage(
            role="system",
            content=english_result.display_message,
            timestamp=timestamp,
            metadata={
                "kind": "translation",
                "spanish_translation": english_result.spanish_translation,
                "original_english": english_result.original_english,
                "vocabulary_gaps": [
                    {
                        "english": gap.english_word,
                        "spanish": gap.spanish_word,
                        "concept_id": gap.concept_id,
                    }
                    for gap in english_result.vocabulary_gaps
                ],
            },
        )
        messages.append(system_msg)
        for gap in english_result.vocabulary_gaps:
            store_vocabulary_gap(gap.english_word, gap.spanish_word, gap.concept_id)

    # Build card to check hard cap
    card = ConversationCard(
        topic=topic,
        concept=concept_id,
        difficulty=difficulty,
        opener=messages[0].content if messages else "",
        messages=messages,
        max_turns=8 if conversation_type == "placement" else 4,
        persona_name=persona.name,
    )

    # End if hard cap reached OR LLM says conversation is done
    hard_cap = engine.should_end(card)
    is_ended = hard_cap or not result.should_continue

    if not is_ended:
        # Add Marta's reply
        ai_msg = ConversationMessage(
            role="ai", content=result.ai_reply, timestamp=now_iso()
        )
        messages.append(ai_msg)

    # Update DB
    messages_json = json.dumps([m.to_dict() for m in messages])
    corrections_json = json.dumps(
        [
            {
                "original": c.original,
                "corrected": c.corrected,
                "explanation": c.explanation,
                "concept_id": c.concept_id,
            }
            for m in messages
            if m.corrections
            for c in m.corrections
        ]
    )

    with _open_connection() as conn:
        user_id = _uid()
        conn.execute(
            """
            UPDATE flow_conversations
            SET messages_json = ?, turn_count = ?, completed = ?, corrections_json = ?
            WHERE user_id = ? AND id = ?
            """,
            (
                messages_json,
                len(messages),
                int(is_ended),
                corrections_json,
                user_id,
                conversation_id,
            ),
        )
        conn.commit()

    context = {
        "session_id": session_id,
        "conversation_id": conversation_id,
        "card": card,
        "concept_name": _get_concept_name(concept_id),
        "is_ended": is_ended,
        "hint": result.hint,
        "persona_name": persona.name,
        "persona_id": persona.id,
        "conversation_type": conversation_type,
    }
    return templates.TemplateResponse(
        request, "partials/flow_conversation.html", context
    )


@router.post("/flow/conversation/skip", response_class=HTMLResponse)
async def conversation_skip(
    request: Request,
    session_id: int = Form(...),
    conversation_id: int = Form(...),
) -> Response:
    from .db import _open_connection

    with _open_connection() as conn:
        user_id = _uid()
        conn.execute(
            """
            UPDATE flow_conversations
            SET completed = 1
            WHERE user_id = ? AND id = ?
            """,
            (user_id, conversation_id),
        )
        conn.commit()

    return await flow_card(request, session_id=session_id)


@router.get("/flow/conversation/summary", response_class=HTMLResponse)
async def conversation_summary(
    request: Request,
    conversation_id: int = Query(...),
    session_id: int = Query(...),
) -> Response:
    """Post-conversation review with explicit corrections."""
    from .conversation import (
        ConversationCard,
        ConversationEngine,
        ConversationMessage,
    )
    from .db import _open_connection

    engine = ConversationEngine()

    with _open_connection() as conn:
        user_id = _uid()
        row = conn.execute(
            "SELECT * FROM flow_conversations WHERE user_id = ? AND id = ?",
            (user_id, conversation_id),
        ).fetchone()

    if row is None:
        return HTMLResponse("<p>Conversation not found.</p>", status_code=404)

    try:
        topic = str(row["topic"])
        concept_id = str(row["concept_id"] or "")
        difficulty = int(row["difficulty"]) if row["difficulty"] is not None else 1
        conversation_type = str(row["conversation_type"] or "general_chat")
        persona = load_persona(row["persona_id"])
        type_instruction = get_type_instruction(
            conversation_type,
            concept_id=concept_id,
            topic=topic,
            persona_id=persona.id,
            starting_level=difficulty if conversation_type == "placement" else None,
        )
        persona_prompt = _compose_persona_prompt(
            persona, type_instruction=type_instruction
        )
        existing_messages = json.loads(row["messages_json"])
        messages = [ConversationMessage.from_dict(m) for m in existing_messages]

        card = ConversationCard(
            topic=topic,
            concept=concept_id,
            difficulty=difficulty,
            opener=messages[0].content if messages else "",
            messages=messages,
            max_turns=8 if conversation_type == "placement" else 4,
            persona_name=persona.name,
        )

        summary = engine.generate_summary(
            card, persona_prompt=persona_prompt, persona_name=persona.name
        )

        evaluation = evaluate_conversation(
            messages=messages,
            concept_id=concept_id,
            topic=topic,
            difficulty=difficulty,
            persona_id=row["persona_id"],
            conversation_type=conversation_type,
            target_concept_id=concept_id,
        )

        enjoyment = compute_enjoyment_score(
            messages=messages,
            max_turns=card.max_turns,
            engagement_quality_from_llm=evaluation.engagement_quality
            if evaluation
            else 0.5,
        )
        user_message_objects = [m for m in messages if m.role == "user"]
        avg_msg_len = (
            sum(len((m.content or "").split()) for m in user_message_objects)
            / len(user_message_objects)
            if user_message_objects
            else 0.0
        )
        was_early_exit = card.user_turn_count < card.max_turns
        topic_id = None  # TODO: wire this once conversation topic_id is persisted.

        try:
            update_persona_engagement(
                persona_id=persona.id,
                topic_id=topic_id,
                enjoyment_score=enjoyment,
                avg_message_length=avg_msg_len,
                turn_count=card.turn_count,
                was_early_exit=was_early_exit,
            )
        except Exception as engagement_exc:
            print(f"[engagement] Failed to update persona engagement: {engagement_exc}")

        # Conversation is the primary source of interest signals.
        # Map conversation topic/concept -> interest topic_id and record one signal.
        try:
            conv_topic_id = get_topic_id_for_conversation(topic, concept_id)
            if conv_topic_id is not None:
                conv_signal = CardSignal(
                    topic_id=conv_topic_id,
                    was_correct=(not was_early_exit and enjoyment >= 0.45),
                    dwell_time_ms=None,
                    response_time_ms=None,
                    card_id=None,
                    session_id=session_id,
                    concept_id=concept_id,
                    card_type="conversation",
                )
                InterestTracker().update_from_card_signal(conv_signal)
        except Exception as interest_exc:
            print(f"[interest] Failed to record conversation signal: {interest_exc}")

        # Harvest vocabulary from user messages — every Spanish word they
        # produced gets tracked. No intro card needed; they already used it.
        from .words import harvest_conversation_words

        user_msgs = [m.content for m in messages if m.role == "user"]
        harvest_conversation_words(user_msgs, concept_id=concept_id or None)

        # Apply BKT updates based on concept evidence
        for evidence in evaluation.concepts_demonstrated:
            ck = get_concept_knowledge(evidence.concept_id)
            if ck is None:
                continue
            mastery = ck.p_mastery
            for _ in range(max(0, evidence.correct_count)):
                mastery = bkt_update(mastery, is_correct=True)
                update_concept_knowledge(evidence.concept_id, mastery, is_correct=True)
            incorrect = max(0, evidence.usage_count - evidence.correct_count)
            for _ in range(incorrect):
                mastery = bkt_update(mastery, is_correct=False)
                update_concept_knowledge(evidence.concept_id, mastery, is_correct=False)

        if conversation_type == "concept_required":
            required = evaluation.concept_required_result
            target = str(required.get("target_concept") or concept_id)
            produced = bool(required.get("produced"))
            correct_uses = max(0, int(required.get("correct_uses") or 0))
            incorrect_uses = max(0, int(required.get("incorrect_uses") or 0))
            target_ck = get_concept_knowledge(target)
            if target_ck is not None:
                mastery = target_ck.p_mastery
                if produced and correct_uses > 0:
                    for _ in range(correct_uses):
                        mastery = bkt_update(mastery, is_correct=True, p_transit=0.18)
                        update_concept_knowledge(target, mastery, is_correct=True)
                if produced and incorrect_uses > 0:
                    for _ in range(incorrect_uses):
                        mastery = bkt_update(mastery, is_correct=False)
                        update_concept_knowledge(target, mastery, is_correct=False)
                if not produced:
                    # Mild negative signal for avoidance without harsh penalization.
                    mastery = bkt_update(mastery, is_correct=False, p_transit=0.03)
                    update_concept_knowledge(target, mastery, is_correct=False)

        try:
            if evaluation.persona_observations:
                store_persona_memories(
                    persona_id=persona.id,
                    observations=evaluation.persona_observations,
                    conversation_id=conversation_id,
                )
            if evaluation.user_facts:
                store_user_facts(
                    facts=evaluation.user_facts,
                    conversation_id=conversation_id,
                )
        except Exception:
            # Memory persistence should never block the summary flow.
            pass

        # Save score to DB
        evaluation_json = json.dumps(asdict(evaluation), ensure_ascii=False)
        with _open_connection() as conn:
            user_id = _uid()
            conn.execute(
                "UPDATE flow_conversations SET score = ?, completed = 1, evaluation_json = ? WHERE user_id = ? AND id = ?",
                (summary.score, evaluation_json, user_id, conversation_id),
            )
            conn.commit()

        placement_summary: dict[str, Any] | None = None
        if conversation_type == "placement":
            placement_summary = apply_placement_results(evaluation)
            set_user_onboarded(True)

        context = {
            "session_id": session_id,
            "conversation_id": conversation_id,
            "card": card,
            "summary": summary,
            "concept_name": _get_concept_name(concept_id),
            "score_pct": int(summary.score * 100),
            "persona_name": persona.name,
            "evaluation": evaluation,
        }
        if placement_summary is not None:
            context["placement"] = placement_summary
            context["starting_concept_name"] = _pick_next_learning_concept_name()
            # If arrived via HTMX, redirect so the full page renders properly
            if request.headers.get("HX-Request"):
                resp = Response(status_code=200)
                resp.headers["HX-Redirect"] = (
                    f"/flow/conversation/summary?conversation_id={conversation_id}&session_id={session_id}"
                )
                return resp
            return templates.TemplateResponse(
                request, "flow_placement_results.html", context
            )
        return templates.TemplateResponse(
            request, "partials/flow_conversation_summary.html", context
        )
    except Exception as exc:
        import traceback

        traceback.print_exc()
        return HTMLResponse(
            f'<div class="rounded-2xl bg-red-500/10 p-6 ring-1 ring-red-500/30 text-center">'
            f'<p class="text-sm text-red-300 mb-3">Summary failed: {escape(str(exc))}</p>'
            f'<button hx-get="/flow/card?session_id={session_id}" hx-target="#flow-card-slot" hx-swap="innerHTML"'
            f' class="rounded-xl bg-slate-700 px-5 py-3 text-sm font-bold text-slate-200 hover:bg-slate-600">'
            f"Skip to Next Card</button></div>",
            status_code=200,
        )


@router.post("/flow/dev/feedback", response_class=HTMLResponse)
async def dev_feedback(
    request: Request,
    card_type: str = Form(...),
    card_id: int = Form(default=0),
    concept_id: str = Form(default=""),
    persona_id: str = Form(default=""),
    conversation_type: str = Form(default=""),
    rating: int = Form(default=0),
    issue_tags: str = Form(default=""),
    note: str = Form(default=""),
    context_json: str = Form(default="{}"),
    session_id: int = Form(default=0),
    conversation_id: int = Form(default=0),
) -> Response:
    """Store dev feedback for the current card/conversation."""
    timestamp = now_iso()
    payload = context_json.strip() or "{}"
    if payload == "{}":
        state = _build_dev_state_payload(
            session_id=session_id if session_id > 0 else None,
            concept_id=concept_id or None,
            conversation_id=conversation_id if conversation_id > 0 else None,
        )
        payload = json.dumps(state, ensure_ascii=False)
    with _open_connection() as conn:
        conn.execute(
            """
            INSERT INTO dev_feedback (
                card_type, card_id, concept_id, persona_id, conversation_type,
                rating, issue_tags, note, context_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                card_type.strip(),
                int(card_id) if card_id else None,
                concept_id.strip() or None,
                persona_id.strip() or None,
                conversation_type.strip() or None,
                max(0, min(5, int(rating))),
                issue_tags.strip() or None,
                note.strip() or None,
                payload,
                timestamp,
            ),
        )
        conn.commit()
    return HTMLResponse("<span>✓ Saved</span>")


@router.get("/flow/dev/state", response_class=HTMLResponse)
async def dev_state(
    request: Request,
    session_id: int = Query(...),
    concept_id: str = Query(default=""),
    conversation_id: int = Query(default=0),
    card_type: str = Query(default=""),
    persona_id: str = Query(default=""),
    conversation_type: str = Query(default=""),
    view: str = Query(default="full"),
) -> Response:
    """Return current engine state as an HTML fragment for the dev panel."""
    state = _build_dev_state_payload(
        session_id=session_id,
        concept_id=concept_id or None,
        conversation_id=conversation_id if conversation_id > 0 else None,
        card_type=card_type or None,
        persona_id=persona_id or None,
        conversation_type=conversation_type or None,
    )
    normalized_view = view.strip().lower()
    if normalized_view == "summary":
        return HTMLResponse(_render_dev_state_html(state, include_all_concepts=False))
    if normalized_view == "concepts":
        return HTMLResponse(_render_dev_concepts_html(state))
    return HTMLResponse(_render_dev_state_html(state, include_all_concepts=True))


@router.post("/flow/dev/set-weights", response_class=HTMLResponse)
async def dev_set_weights(
    w_spot: int = Form(default=30),
    w_practice: int = Form(default=50),
    w_new: int = Form(default=20),
) -> Response:
    spot = max(0.0, min(1.0, w_spot / 100.0))
    practice = max(0.0, min(1.0, w_practice / 100.0))
    new = max(0.0, min(1.0, w_new / 100.0))
    set_dev_override("bucket_weight_spot_check", f"{spot:.4f}")
    set_dev_override("bucket_weight_practice", f"{practice:.4f}")
    set_dev_override("bucket_weight_new", f"{new:.4f}")
    return HTMLResponse("<span>Weights updated</span>")


@router.post("/flow/dev/set-override", response_class=HTMLResponse)
async def dev_set_override(
    key: str = Form(...),
    value: str = Form(default=""),
) -> Response:
    normalized_key = key.strip()
    normalized_value = value.strip()
    if not normalized_key:
        return HTMLResponse("<span>Missing key</span>", status_code=400)
    if normalized_value:
        set_dev_override(normalized_key, normalized_value)
    else:
        delete_dev_override(normalized_key)
    return HTMLResponse(f"<span>Set {escape(normalized_key)}</span>")


@router.post("/flow/dev/reset-concept", response_class=HTMLResponse)
async def dev_reset_concept(concept_id: str = Form(...)) -> Response:
    cid = concept_id.strip()
    if not cid:
        return HTMLResponse("<span>Missing concept_id</span>", status_code=400)
    with _open_connection() as conn:
        user_id = _uid()
        conn.execute(
            """
            UPDATE concept_knowledge
            SET p_mastery = 0.0, n_attempts = 0, n_correct = 0, n_wrong = 0, teach_shown = 0,
                last_seen_at = NULL, updated_at = ?
            WHERE user_id = ? AND concept_id = ?
            """,
            (now_iso(), user_id, cid),
        )
        conn.commit()
    return HTMLResponse(f"<span>Reset {escape(cid)}</span>")


@router.post("/flow/dev/force-persona", response_class=HTMLResponse)
async def dev_force_persona(persona_id: str = Form(...)) -> Response:
    pid = persona_id.strip()
    if not pid:
        delete_dev_override("force_next_persona")
        return HTMLResponse("<span>Cleared forced persona</span>")
    set_dev_override("force_next_persona", pid)
    return HTMLResponse(f"<span>Next persona: {escape(pid)}</span>")


@router.post("/flow/dev/force-conversation", response_class=HTMLResponse)
async def dev_force_conversation() -> Response:
    set_dev_override("force_next_card_type", "conversation")
    return HTMLResponse("<span>Next card forced to conversation</span>")


@router.post("/flow/dev/rerun-placement", response_class=HTMLResponse)
async def dev_rerun_placement() -> Response:
    set_user_onboarded(False)
    return HTMLResponse("<span>Placement reset. Open /flow/onboarding</span>")


@router.post("/flow/dev/skip-placement", response_class=HTMLResponse)
async def dev_skip_placement() -> Response:
    set_user_onboarded(True)
    return HTMLResponse("<span>Placement skipped. Flow unlocked.</span>")


@router.post("/flow/dev/reset-all", response_class=HTMLResponse)
async def dev_reset_all() -> Response:
    from .db import reset_learning_progress

    reset_learning_progress()
    from .concepts import seed_concepts_to_db

    seed_concepts_to_db()
    return HTMLResponse("<span>Reset all progress</span>")


# ── Prompt editing endpoints ────────────────────────────────────────────────


@router.get("/flow/dev/prompts", response_class=HTMLResponse)
async def dev_prompts_list(request: Request) -> Response:
    """Return the list of editable prompts for the dev panel."""
    items = prompt_config.get_all_editable_keys()
    return templates.TemplateResponse(
        request,
        "partials/dev_prompts.html",
        {"items": items},
    )


@router.post("/flow/dev/prompt-save", response_class=HTMLResponse)
async def dev_prompt_save(
    key: str = Form(...),
    value: str = Form(default=""),
    persist: str = Form(default=""),
) -> Response:
    """Save a prompt edit — either as a runtime override or persisted to YAML."""
    k = key.strip()
    v = value.strip()
    if not k:
        return HTMLResponse(
            "<span class='text-red-400'>Missing key</span>", status_code=400
        )
    if persist == "1":
        # Write directly to prompts.yaml
        prompt_config.save_to_yaml(k, v)
        prompt_config.invalidate_cache()
        return HTMLResponse(
            f"<span class='text-emerald-300'>Saved to YAML: {escape(k)}</span>"
        )
    else:
        # Runtime override via dev_overrides table
        if v:
            set_dev_override(f"prompt:{k}", v)
        else:
            delete_dev_override(f"prompt:{k}")
        prompt_config.invalidate_cache()
        return HTMLResponse(
            f"<span class='text-emerald-300'>Override set: {escape(k)}</span>"
        )


@router.post("/flow/dev/prompt-reset", response_class=HTMLResponse)
async def dev_prompt_reset(key: str = Form(...)) -> Response:
    """Clear a runtime prompt override, reverting to YAML value."""
    k = key.strip()
    if k:
        delete_dev_override(f"prompt:{k}")
        prompt_config.invalidate_cache()
    return HTMLResponse(f"<span class='text-emerald-300'>Reset: {escape(k)}</span>")


@router.post("/flow/clear-mcq-cache", response_class=HTMLResponse)
async def clear_mcq_cache_endpoint(
    concept_id: str = Form(default=""),
) -> Response:
    """Clear AI-generated MCQ cache so questions regenerate with improved prompts."""
    cid = concept_id.strip() or None
    deleted = clear_mcq_cache(concept_id=cid, source="ai")
    label = f"concept '{cid}'" if cid else "all concepts"
    return HTMLResponse(
        f"<p>Cleared {deleted} cached MCQs for {label}. Fresh questions will generate on next play.</p>"
    )


def _build_dev_state_payload(
    *,
    session_id: int | None,
    concept_id: str | None,
    conversation_id: int | None,
    card_type: str | None = None,
    persona_id: str | None = None,
    conversation_type: str | None = None,
) -> dict[str, Any]:
    concepts = load_concepts()
    knowledge = get_all_concept_knowledge()
    session = get_session(session_id) if session_id else None
    state = build_session_state(session_id) if session_id else None
    overrides = get_all_dev_overrides()

    current_concept_id = concept_id or ""
    if not current_concept_id and conversation_id:
        with _open_connection() as conn:
            row = conn.execute(
                "SELECT concept_id FROM flow_conversations WHERE user_id = ? AND id = ?",
                (_uid(), conversation_id),
            ).fetchone()
        if row:
            current_concept_id = str(row["concept_id"] or "")

    current_knowledge = (
        knowledge.get(current_concept_id) if current_concept_id else None
    )
    concept_name = (
        concepts[current_concept_id].name
        if current_concept_id in concepts
        else current_concept_id
    )
    is_current_mastered = bool(current_knowledge) and is_mastered(
        current_knowledge.p_mastery, current_knowledge.n_attempts
    )

    with _open_connection() as conn:
        user_id = _uid()
        conversation_count_row = (
            conn.execute(
                "SELECT COUNT(*) AS c FROM flow_conversations WHERE user_id = ? AND session_id = ?",
                (user_id, session_id),
            ).fetchone()
            if session_id
            else None
        )
        total_words_row = conn.execute("SELECT COUNT(*) AS c FROM words").fetchone()
        top_tapped_rows = conn.execute(
            """
            SELECT spanish_word, COUNT(*) AS taps
            FROM word_taps
            WHERE user_id = ?
            GROUP BY spanish_word
            ORDER BY taps DESC, spanish_word ASC
            LIMIT 5
            """,
            (user_id,),
        ).fetchall()
        engagement_rows = conn.execute(
            """
            SELECT persona_id, conversation_count, avg_enjoyment_score, last_conversation_at
            FROM persona_engagement
            WHERE user_id = ? AND topic_id IS NULL
            ORDER BY avg_enjoyment_score DESC
            """,
            (user_id,),
        ).fetchall()
        latest_eval_row = None
        if conversation_id:
            latest_eval_row = conn.execute(
                "SELECT evaluation_json, persona_id, conversation_type FROM flow_conversations WHERE user_id = ? AND id = ?",
                (user_id, conversation_id),
            ).fetchone()
        if latest_eval_row is None:
            latest_eval_row = (
                conn.execute(
                    """
                SELECT evaluation_json, persona_id, conversation_type
                FROM flow_conversations
                WHERE user_id = ? AND session_id = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                    (user_id, session_id),
                ).fetchone()
                if session_id
                else None
            )

    personas = load_all_personas()
    top_interests = InterestTracker().get_top_interests(3)
    persona_engagement: list[dict[str, Any]] = []
    for p in personas:
        row = next((r for r in engagement_rows if str(r["persona_id"]) == p.id), None)
        avg_enjoyment = float(row["avg_enjoyment_score"]) if row else 0.5
        conv_count = int(row["conversation_count"]) if row else 0
        last_at = (
            str(row["last_conversation_at"])
            if row and row["last_conversation_at"]
            else None
        )
        novelty = _persona_novelty_from_timestamp(last_at, conv_count)
        selection_score = avg_enjoyment * 0.6 + novelty * 0.3 + 0.05
        persona_engagement.append(
            {
                "persona_id": p.id,
                "avg_enjoyment": avg_enjoyment,
                "conversation_count": conv_count,
                "last_conversation_at": last_at,
                "novelty_bonus": novelty,
                "selection_score_estimate": selection_score,
            }
        )

    evaluation_data: dict[str, Any] = {}
    if latest_eval_row and latest_eval_row["evaluation_json"]:
        try:
            evaluation_data = json.loads(str(latest_eval_row["evaluation_json"]))
        except json.JSONDecodeError:
            evaluation_data = {"raw": str(latest_eval_row["evaluation_json"])}
    if latest_eval_row:
        evaluation_data.setdefault("persona_id", latest_eval_row["persona_id"])
        evaluation_data.setdefault(
            "conversation_type", latest_eval_row["conversation_type"]
        )

    concept_overview: list[dict[str, Any]] = []
    for concept_key, concept in sorted(
        concepts.items(), key=lambda item: (item[1].difficulty_level, item[1].name)
    ):
        ck = knowledge.get(concept_key)
        p_mastery = ck.p_mastery if ck else 0.0
        attempts = ck.n_attempts if ck else 0
        if ck and is_mastered(ck.p_mastery, ck.n_attempts):
            status = "MASTERED"
        elif attempts > 0:
            status = "learning"
        elif prerequisites_met(concept_key, knowledge, concepts):
            status = "new"
        else:
            status = "locked"
        concept_overview.append(
            {
                "id": concept_key,
                "name": concept.name,
                "p_mastery": p_mastery,
                "attempts": attempts,
                "status": status,
                "is_current": concept_key == current_concept_id,
            }
        )

    session_accuracy = (
        (session.correct_count / session.cards_answered)
        if session and session.cards_answered > 0
        else 0.0
    )
    user_level = get_user_level(knowledge, concepts)
    selected_card_type = (card_type or "").strip()
    selected_persona_id = (persona_id or "").strip()
    selected_conversation_type = (conversation_type or "").strip()
    selection_reason = _infer_card_selection_reason(
        card_type=selected_card_type,
        current_concept=current_knowledge,
        current_bucket=_guess_bucket(current_knowledge),
    )
    return {
        "session_id": session_id,
        "current_card": {
            "card_type": selected_card_type,
            "persona_id": selected_persona_id,
            "conversation_type": selected_conversation_type,
            "selection_reason": selection_reason,
            "top_interests": [t.name for t in top_interests],
        },
        "current_concept": {
            "id": current_concept_id,
            "name": concept_name,
            "p_mastery": current_knowledge.p_mastery if current_knowledge else 0.0,
            "n_attempts": current_knowledge.n_attempts if current_knowledge else 0,
            "n_correct": current_knowledge.n_correct if current_knowledge else 0,
            "n_wrong": current_knowledge.n_wrong if current_knowledge else 0,
            "is_mastered": is_current_mastered,
            "bucket_guess": _guess_bucket(current_knowledge),
        },
        "session_stats": {
            "cards_answered": session.cards_answered if session else 0,
            "correct_count": session.correct_count if session else 0,
            "accuracy": session_accuracy,
            "current_streak": state.current_streak if state else 0,
            "conversations_completed": int(conversation_count_row["c"])
            if conversation_count_row
            else 0,
        },
        "persona_state": {
            "excluded_persona_id": (get_last_conversation_info(session_id) or {}).get(
                "persona_id"
            ),
            "engagement_rows": persona_engagement,
        },
        "word_tracking": {
            "total_words": int(total_words_row["c"]) if total_words_row else 0,
            "top_tapped_words": [dict(row) for row in top_tapped_rows],
        },
        "evaluation": evaluation_data,
        "user_level": user_level,
        "overrides": overrides,
        "concept_overview": concept_overview,
    }


def _render_dev_concepts_html(state: dict[str, Any]) -> str:
    concept_rows = state.get("concept_overview", []) or []
    concept_lines: list[str] = []
    for row in concept_rows:
        status = str(row.get("status") or "")
        if status == "MASTERED":
            icon = "✅"
            cls = "text-emerald-300"
        elif status == "learning":
            icon = "📚"
            cls = "text-amber-300"
        elif status == "new":
            icon = "🆕"
            cls = "text-sky-300"
        else:
            icon = "🔒"
            cls = "text-slate-400"
        current_mark = " ← current" if row.get("is_current") else ""
        concept_lines.append(
            f'<div class="{cls}">{icon} '
            f"{escape(str(row.get('id') or ''))}  "
            f"{float(row.get('p_mastery') or 0.0):.2f}  "
            f"{int(row.get('attempts') or 0)}att  "
            f"{escape(status)}{escape(current_mark)}</div>"
        )
    concepts_html = "".join(concept_lines) or "<div>no concepts</div>"
    return (
        '<div class="mb-3 border-t border-slate-700 pt-2">'
        '<div class="font-bold text-slate-300 mb-1">ALL CONCEPTS</div>'
        f"{concepts_html}"
        "</div>"
    )


def _render_dev_state_html(
    state: dict[str, Any], *, include_all_concepts: bool = True
) -> str:
    def section(title: str, body: str, header_class: str = "text-slate-100") -> str:
        return (
            '<div class="mb-3 border-t border-slate-700 pt-2">'
            f'<div class="font-bold {header_class} mb-1">{escape(title)}</div>'
            f"{body}"
            "</div>"
        )

    current = state.get("current_concept", {})
    current_card = state.get("current_card", {}) or {}
    user_level = state.get("user_level", {}) or {}
    card_html = (
        f"<div>Concept: {escape(str(current.get('id') or '(none)'))}</div>"
        f"<div>Card type: {escape(str(current_card.get('card_type') or '(none)'))}  "
        f"Persona: {escape(str(current_card.get('persona_id') or '(none)'))}  "
        f"Conv type: {escape(str(current_card.get('conversation_type') or '(none)'))}</div>"
        f"<div>Why chosen: {escape(str(current_card.get('selection_reason') or 'n/a'))}</div>"
        f"<div>Interest focus: {escape(', '.join(current_card.get('top_interests') or []) or 'n/a')}</div>"
    )
    tier_mastery = (
        user_level.get("tier_mastery", {}) if isinstance(user_level, dict) else {}
    )
    level_html = (
        f"<div>Level: {int(user_level.get('level') or 1)}  CEFR: {escape(str(user_level.get('cefr') or 'A1'))}</div>"
        f"<div>Session difficulty: {int(user_level.get('session_difficulty') or 1)}</div>"
        f"<div>Tier mastery: "
        f"T1 {float(tier_mastery.get(1) or tier_mastery.get('1') or 0.0) * 100:.0f}%  "
        f"T2 {float(tier_mastery.get(2) or tier_mastery.get('2') or 0.0) * 100:.0f}%  "
        f"T3 {float(tier_mastery.get(3) or tier_mastery.get('3') or 0.0) * 100:.0f}%"
        f"</div>"
        f"<div>Mastered: {int(user_level.get('total_mastered') or 0)}/{int(user_level.get('total_concepts') or 0)}</div>"
    )

    if not str(current.get("id") or "").strip():
        current_lines = [
            "<div class='text-slate-400'>(none — card not loaded yet)</div>"
        ]
    else:
        current_lines = [
            f"<div>{escape(str(current.get('id') or 'n/a'))} ({escape(str(current.get('name') or ''))})</div>",
            (
                "<div>"
                f"p_mastery: {float(current.get('p_mastery') or 0.0):.2f}  "
                f"attempts: {int(current.get('n_attempts') or 0)}  "
                f"bucket: {escape(str(current.get('bucket_guess') or 'n/a'))}"
                "</div>"
            ),
            (
                "<div>"
                f"correct: {int(current.get('n_correct') or 0)}  "
                f"wrong: {int(current.get('n_wrong') or 0)}  "
                f"mastered: {'Yes' if current.get('is_mastered') else 'No'}"
                "</div>"
            ),
        ]
    current_html = "".join(current_lines)

    session_stats = state.get("session_stats", {})
    session_html = (
        "<div>"
        f"Cards: {int(session_stats.get('cards_answered') or 0)}  "
        f"Correct: {int(session_stats.get('correct_count') or 0)}  "
        f"Accuracy: {float(session_stats.get('accuracy') or 0.0) * 100:.0f}%"
        "</div>"
        "<div>"
        f"Streak: {int(session_stats.get('current_streak') or 0)}  "
        f"Conversations: {int(session_stats.get('conversations_completed') or 0)}"
        "</div>"
    )

    persona_state = state.get("persona_state", {})
    persona_rows = persona_state.get("engagement_rows", []) or []
    persona_lines: list[str] = []
    best_id = None
    best_score = -1.0
    for row in persona_rows:
        score = float(row.get("selection_score_estimate") or 0.0)
        if score > best_score:
            best_score = score
            best_id = str(row.get("persona_id") or "")
    for row in persona_rows:
        pid = str(row.get("persona_id") or "")
        marker = " ← next likely" if pid == best_id and pid else ""
        row_class = (
            "text-slate-500"
            if pid == str(persona_state.get("excluded_persona_id") or "")
            else "text-slate-200"
        )
        persona_lines.append(
            f'<div class="{row_class}">'
            f"{escape(pid):<12} "
            f"enjoy:{float(row.get('avg_enjoyment') or 0.0):.2f}  "
            f"convos:{int(row.get('conversation_count') or 0)}  "
            f"novelty:{float(row.get('novelty_bonus') or 0.0):.2f}  "
            f"score:{float(row.get('selection_score_estimate') or 0.0):.2f}"
            f"{escape(marker)}"
            "</div>"
        )
    persona_lines.append(
        f"<div>Excluded (last used): {escape(str(persona_state.get('excluded_persona_id') or 'none'))}</div>"
    )
    personas_html = "".join(persona_lines)

    words = state.get("word_tracking", {})
    top_tapped = words.get("top_tapped_words", []) or []
    top_tapped_text = (
        " ".join(
            f"{escape(str(item.get('spanish_word') or ''))}({int(item.get('taps') or 0)})"
            for item in top_tapped
        )
        or "none"
    )
    words_html = (
        f"<div>Total tracked: {int(words.get('total_words') or 0)}</div>"
        f"<div>Top tapped: {top_tapped_text}</div>"
    )

    evaluation = state.get("evaluation", {}) or {}
    concepts_demo = evaluation.get("concepts_demonstrated", []) or []
    concept_bits: list[str] = []
    for item in concepts_demo[:6]:
        if not isinstance(item, dict):
            continue
        cid = str(item.get("concept_id") or "")
        ok = int(item.get("correct_count") or 0)
        used = int(item.get("usage_count") or 0)
        wrong = max(0, used - ok)
        concept_bits.append(f"{cid}(✓{ok} ✗{wrong})")
    vocab_text = ", ".join((evaluation.get("vocabulary_used") or [])[:8]) or "none"
    facts_text = ", ".join((evaluation.get("user_facts") or [])[:6]) or "none"
    cefr = evaluation.get("estimated_cefr") or {}
    cefr_text = (
        ", ".join(f"{k}:{v}" for k, v in list(cefr.items())[:4])
        if isinstance(cefr, dict)
        else str(cefr)
    )
    eval_html = (
        (
            f"<div>Persona: {escape(str(evaluation.get('persona_id') or 'n/a'))}  "
            f"Type: {escape(str(evaluation.get('conversation_type') or 'n/a'))}</div>"
            f"<div>Engagement: {float(evaluation.get('engagement_quality') or 0.0):.2f}  CEFR: {escape(cefr_text or 'n/a')}</div>"
            f"<div>Concepts: {escape(', '.join(concept_bits) or 'none')}</div>"
            f"<div>Vocab: {escape(vocab_text)}</div>"
            f"<div>Facts: {escape(facts_text)}</div>"
        )
        if evaluation
        else ""
    )

    overrides = state.get("overrides", {}) or {}
    override_lines = [
        f"<div>{escape(str(k))}: {escape(str(v))}</div>"
        for k, v in sorted(overrides.items())
    ]
    overrides_html = "".join(override_lines)

    return (
        '<div class="text-xs text-slate-200 font-mono">'
        + section("TOP CONTEXT", card_html, "text-cyan-300")
        + section("USER LEVEL", level_html, "text-amber-300")
        + section("CURRENT CONCEPT", current_html, "text-emerald-300")
        + section("SESSION", session_html, "text-sky-300")
        + section("PERSONAS", personas_html, "text-violet-300")
        + section("WORDS", words_html, "text-indigo-300")
        + (section("LAST EVALUATION", eval_html, "text-amber-300") if eval_html else "")
        + (
            section("OVERRIDES", overrides_html, "text-orange-300")
            if overrides_html
            else ""
        )
        + (_render_dev_concepts_html(state) if include_all_concepts else "")
        + "</div>"
    )


def _infer_card_selection_reason(
    *,
    card_type: str,
    current_concept: Any,
    current_bucket: str,
) -> str:
    if card_type in {"conversation", "story_comprehension"}:
        return "Conversation cadence trigger or forced override."
    if card_type == "teach":
        return "New concept detected; teach card shown before practice."
    if card_type in {"word_intro", "word_practice", "word_match"}:
        return "Word-tracking progression selected for this concept."
    if card_type == "sentence_builder":
        return "Sentence-building card selected from concept example sentences."
    if card_type == "emoji_association":
        return "Emoji-based vocabulary association selected from learned words."
    if card_type == "fill_blank":
        return "Grammar fill-in-the-blank selected from concept-specific prompts."
    if card_type == "mcq":
        return f"MCQ selected from {current_bucket} bucket."
    if current_concept is not None and getattr(current_concept, "n_attempts", 0) == 0:
        return "New concept flow path."
    return "Default scheduler path."


def _guess_bucket(ck: Any) -> str:
    if ck is None:
        return "new"
    if ck.n_attempts == 0:
        return "new"
    if is_mastered(ck.p_mastery, ck.n_attempts):
        return "spot-check"
    return "practice"


def _persona_novelty_from_timestamp(
    last_conversation_at: str | None, conversation_count: int
) -> float:
    if conversation_count <= 0 or not last_conversation_at:
        return 1.0
    try:
        last_dt = datetime.fromisoformat(last_conversation_at)
    except ValueError:
        return 1.0
    if last_dt.tzinfo is None:
        last_dt = last_dt.replace(tzinfo=timezone.utc)
    now_dt = datetime.now(timezone.utc)
    days_since = max(0.0, (now_dt - last_dt).total_seconds() / 86400.0)
    return min(1.0, days_since / 5.0)


def _pick_placement_persona_id() -> str:
    personas = load_all_personas()
    if not personas:
        return "marta_fallback"
    preferred_ids = ("marta", "abuela_rosa")
    for preferred_id in preferred_ids:
        if any(p.id == preferred_id for p in personas):
            return preferred_id
    return personas[0].id


def _pick_placement_concept(starting_level: int) -> str:
    concepts = load_concepts()
    level_preferred: dict[int, tuple[str, ...]] = {
        1: (
            "greetings",
            "numbers_1_20",
            "colors_basic",
        ),
        2: (
            "subject_pronouns",
            "nouns_gender",
            "family_vocab",
            "food_vocab",
        ),
        3: (
            "ser_present",
            "tener_present",
            "basic_questions",
            "articles_definite",
        ),
        4: (
            "estar_present",
            "gustar",
            "ir_a",
            "querer",
        ),
    }
    for preferred_id in level_preferred.get(starting_level, ()):
        if preferred_id in concepts:
            return preferred_id

    target_tier = 1 if starting_level <= 1 else (2 if starting_level == 2 else 3)
    candidates = sorted(
        [cid for cid, c in concepts.items() if c.difficulty_level == target_tier],
        key=lambda cid: concepts[cid].name,
    )
    if candidates:
        return candidates[0]
    # Fallback to any concept by tier then name.
    ordered = sorted(
        concepts.items(), key=lambda item: (item[1].difficulty_level, item[1].name)
    )
    return ordered[0][0] if ordered else "greetings"


def _pick_placement_topic(interest_topic_ids: list[int], *, starting_level: int) -> str:
    if interest_topic_ids:
        ids = {int(tid) for tid in interest_topic_ids}
        topics = get_all_interest_topics()
        for topic in topics:
            if int(topic["id"]) in ids:
                return str(topic.get("name") or "la vida diaria")
    top = InterestTracker().get_top_interests(1)
    if top:
        return top[0].name
    if starting_level <= 1:
        return "la vida diaria"
    if starting_level == 2:
        return "rutina y pasatiempos"
    if starting_level == 3:
        return "viajes y trabajo"
    return "opiniones y experiencias"


def _pick_next_learning_concept_name() -> str:
    concepts = load_concepts()
    knowledge = get_all_concept_knowledge()
    for concept_id, concept in sorted(
        concepts.items(), key=lambda item: (item[1].difficulty_level, item[1].name)
    ):
        ck = knowledge.get(concept_id)
        if ck is None:
            continue
        if not is_mastered(ck.p_mastery, ck.n_attempts):
            return concept.name
    first = sorted(concepts.values(), key=lambda c: (c.difficulty_level, c.name))
    return first[0].name if first else "your next concept"


def _get_seen_and_mastered_concepts() -> tuple[set[str], set[str]]:
    knowledge = get_all_concept_knowledge()
    seen = {
        cid
        for cid, ck in knowledge.items()
        if int(ck.n_attempts) > 0 or bool(ck.teach_shown)
    }
    mastered = {
        cid
        for cid, ck in knowledge.items()
        if is_mastered(float(ck.p_mastery), int(ck.n_attempts))
    }
    return seen, mastered


def _build_conversation_guardrails(
    *,
    concept_id: str,
    difficulty: int,
    seen_concepts: set[str] | None = None,
    mastered_concepts: set[str] | None = None,
) -> str:
    concepts = load_concepts()
    seen, mastered = (
        (seen_concepts or set(), mastered_concepts or set())
        if seen_concepts is not None and mastered_concepts is not None
        else _get_seen_and_mastered_concepts()
    )
    allowed_concepts = set(seen) | set(mastered) | {concept_id}

    concept_names: list[str] = []
    for cid in sorted(allowed_concepts):
        concept = concepts.get(cid)
        if concept:
            concept_names.append(concept.name)
        if len(concept_names) >= 10:
            break

    vocab_items: list[str] = []
    if allowed_concepts:
        placeholders = ",".join("?" for _ in allowed_concepts)
        with _open_connection() as conn:
            rows = conn.execute(
                f"""
                SELECT spanish FROM words
                WHERE concept_id IN ({placeholders})
                  AND status IN ('introduced', 'practicing', 'known')
                ORDER BY times_seen DESC, id DESC
                LIMIT 80
                """,
                tuple(sorted(allowed_concepts)),
            ).fetchall()
        vocab_items = [str(row["spanish"]).strip() for row in rows if row["spanish"]]

    vocab_text = ", ".join(vocab_items[:40]) if vocab_items else "hola, sí, no, gracias"
    concept_text = (
        ", ".join(concept_names)
        if concept_names
        else (_get_concept_name(concept_id) or concept_id)
    )
    max_words = 8 if difficulty <= 1 else (12 if difficulty == 2 else 16)

    return (
        f"- PRIORITY CONCEPT: {concept_id} ({_get_concept_name(concept_id)})\n"
        f"- ALLOWED CONCEPT SCOPE: {concept_text}\n"
        f"- ALLOWED VOCAB (prefer strongly): {vocab_text}\n"
        f"- Use short sentences (max {max_words} words).\n"
        "- Ask one simple question at a time.\n"
        "- Do NOT jump to advanced tenses unless the learner uses them first.\n"
        "- If unsure, simplify and reuse prior learner vocabulary."
    )


def _compose_persona_prompt(
    persona: Any, *, type_instruction: str | None = None
) -> str:
    persona_memories: list[str] | None = None
    user_facts: list[str] | None = None
    try:
        if getattr(persona, "id", None):
            persona_memories = get_persona_memories(str(persona.id))
        user_facts = get_user_profile()
    except Exception:
        # Memory loading is additive only. Fall back to base prompt on failures.
        persona_memories = None
        user_facts = None
    prompt = get_persona_prompt(
        persona, persona_memories=persona_memories, user_facts=user_facts
    )
    if type_instruction:
        prompt = f"{prompt}\n\n{type_instruction}"
    return prompt


def _increment_session_cards_answered(session_id: int) -> None:
    session = get_session(session_id)
    if session:
        update_session(session_id, cards_answered=session.cards_answered + 1)


def _start_chat_conversation_card(
    *,
    request: Request,
    session_id: int,
    concept_id: str,
    topic: str,
    difficulty: int,
    conversation_type: str,
    forced_persona_id: str | None = None,
    placement_starting_level: int | None = None,
) -> Response:
    from .conversation import ConversationCard, ConversationEngine, ConversationMessage
    from .db import _open_connection, now_iso

    engine = ConversationEngine()
    seen_concepts, mastered_concepts = _get_seen_and_mastered_concepts()
    if forced_persona_id:
        persona = load_persona(forced_persona_id)
    else:
        last_conv = get_last_conversation_info(session_id)
        exclude_persona_id = last_conv.get("persona_id") if last_conv else None
        persona = select_persona(
            exclude_id=exclude_persona_id,
            difficulty=difficulty,
            seen_concepts=seen_concepts,
            mastered_concepts=mastered_concepts,
        )
    type_instruction = get_type_instruction(
        conversation_type,
        concept_id=concept_id,
        topic=topic,
        persona_id=persona.id,
        starting_level=placement_starting_level,
    )
    persona_prompt = _compose_persona_prompt(persona, type_instruction=type_instruction)
    user_level_info = get_user_level()
    effective_difficulty = int(user_level_info.get("session_difficulty", difficulty))
    conversation_guardrails = _build_conversation_guardrails(
        concept_id=concept_id,
        difficulty=effective_difficulty,
        seen_concepts=seen_concepts,
        mastered_concepts=mastered_concepts,
    )

    opener = engine.generate_opener(
        topic,
        concept_id,
        effective_difficulty,
        persona_prompt=persona_prompt,
        persona_name=persona.name,
        conversation_guardrails=conversation_guardrails,
    )

    timestamp = now_iso()
    opener_msg = ConversationMessage(role="ai", content=opener, timestamp=timestamp)
    messages_json = json.dumps([opener_msg.to_dict()])

    with _open_connection() as conn:
        user_id = _uid()
        cursor = conn.execute(
            """
            INSERT INTO flow_conversations
                (user_id, session_id, topic, messages_json, turn_count, completed, created_at, concept_id, difficulty, persona_id, conversation_type)
            VALUES (?, ?, ?, ?, 1, 0, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                session_id,
                topic,
                messages_json,
                timestamp,
                concept_id,
                effective_difficulty,
                persona.id,
                conversation_type,
            ),
        )
        conn.commit()
        conversation_id = int(cursor.lastrowid)

    # Count this card as soon as it starts so abandon/refresh can't trap
    # the scheduler at the same conversation-frequency boundary.
    _increment_session_cards_answered(session_id)

    card = ConversationCard(
        topic=topic,
        concept=concept_id,
        difficulty=effective_difficulty,
        opener=opener,
        messages=[opener_msg],
        max_turns=8 if conversation_type == "placement" else 4,
        persona_name=persona.name,
    )
    context = {
        "session_id": session_id,
        "conversation_id": conversation_id,
        "card": card,
        "concept_name": _get_concept_name(concept_id),
        "is_ended": False,
        "persona_name": persona.name,
        "persona_id": persona.id,
        "conversation_type": conversation_type,
    }
    return templates.TemplateResponse(
        request, "partials/flow_conversation.html", context
    )


def _render_story_comprehension_card(
    *,
    request: Request,
    session_id: int,
    concept_id: str,
    topic: str,
    difficulty: int,
    conversation_type: str,
) -> Response:
    from .conversation import get_random_topic

    actual_topic = topic or get_random_topic()
    seen_concepts, mastered_concepts = _get_seen_and_mastered_concepts()
    last_conv = get_last_conversation_info(session_id)
    exclude_persona_id = last_conv.get("persona_id") if last_conv else None
    persona = select_persona(
        exclude_id=exclude_persona_id,
        difficulty=difficulty,
        seen_concepts=seen_concepts,
        mastered_concepts=mastered_concepts,
    )
    persona_prompt = _compose_persona_prompt(persona)
    user_level_info = get_user_level()
    effective_difficulty = int(user_level_info.get("session_difficulty", difficulty))

    story_payload = generate_story_card(
        concept_id=concept_id,
        topic=actual_topic,
        difficulty=effective_difficulty,
        persona_prompt=persona_prompt,
        persona_name=persona.name,
    )
    if not isinstance(story_payload, dict):
        # Safe fallback to baseline conversation mode.
        return _start_chat_conversation_card(
            request=request,
            session_id=session_id,
            concept_id=concept_id,
            topic=actual_topic,
            difficulty=effective_difficulty,
            conversation_type="general_chat",
        )

    # Count story cards at start to avoid repeated retriggers when abandoned.
    _increment_session_cards_answered(session_id)

    context = {
        "session_id": session_id,
        "concept_id": concept_id,
        "concept_name": _get_concept_name(concept_id),
        "topic": actual_topic,
        "persona_name": persona.name,
        "persona_id": persona.id,
        "conversation_type": conversation_type,
        "story_payload": story_payload,
        "story_payload_json": json.dumps(story_payload),
    }
    return templates.TemplateResponse(request, "partials/flow_story_card.html", context)


def _render_teach(content: str | None) -> str:
    """Convert markdown teach_content to HTML.

    Uses the nl2br extension so single newlines in the YAML become <br> tags,
    keeping vocab lists and conjugation tables readable without requiring blank
    lines between every entry.
    """
    if not content:
        return ""
    return markdown.markdown(content.strip(), extensions=["nl2br"])


def _get_concept_name(concept_id: str) -> str:
    concepts = load_concepts()
    concept = concepts.get(concept_id)
    return concept.name if concept else concept_id


def _get_concept_teach_html(concept_id: str) -> str:
    concepts = load_concepts()
    concept = concepts.get(concept_id)
    if concept and concept.teach_content:
        return _render_teach(_format_teach_snippet_markdown(concept.teach_content))
    return ""


def _format_teach_snippet_markdown(content: str | None) -> str:
    """Insert readable line breaks for dense one-line snippet content."""
    text = (content or "").strip()
    if not text:
        return ""
    # Respect authored multiline snippets.
    if "\n" in text:
        return text
    # Break before repeated markdown-bold term definitions:
    # **un** — ... **una** — ... -> separate paragraphs.
    text = re.sub(r"\s+(?=\*\*[^*]+\*\*\s+[—-])", "\n\n", text)
    return text


def _get_misconception_hint(misconception_id: str | None) -> str:
    if not misconception_id:
        return ""
    concepts = load_concepts()
    concept = concepts.get(misconception_id)
    if concept:
        return f"Review: {concept.name}"
    return ""


def _build_wrong_explanation(
    *,
    card_type: str,
    chosen_option: str,
    correct_answer: str,
    misconception_hint: str = "",
) -> str:
    if misconception_hint:
        if chosen_option:
            return (
                f"{misconception_hint}. "
                f"\"{chosen_option}\" does not match the concept required by this question."
            )
        return misconception_hint

    if card_type == "sentence_builder":
        return (
            "The word order is not correct for this sentence. "
            "Build the exact Spanish sentence in the right order."
        )
    if card_type == "fill_blank":
        return (
            f"This blank needs \"{correct_answer}\" based on the sentence context."
        )
    if card_type in {"word_practice", "emoji_association", "mcq"}:
        if chosen_option:
            return (
                f"\"{chosen_option}\" is not the correct choice for this prompt. "
                f"The correct answer is \"{correct_answer}\"."
            )
        return f"The correct answer is \"{correct_answer}\"."
    return f"The correct answer is \"{correct_answer}\"."
