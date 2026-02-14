"""FastAPI routes for Flow Mode v2 — concept-based MCQ learning."""

from __future__ import annotations

import json
from html import escape
from datetime import datetime, timezone
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
from .interest import CardSignal, InterestTracker
from .flow_db import (
    clear_mcq_cache,
    get_session,
    mark_teach_shown,
    get_all_concept_knowledge,
    store_vocabulary_gap,
    update_session,
)
from .db import seed_interest_topics
from .concepts import load_concepts
from .bkt import is_mastered
from .lexicon import translate_spanish_word
from .template_helpers import register_template_filters

router = APIRouter()

PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_ROOT.parent.parent
TEMPLATES_DIR = PROJECT_ROOT / "templates"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
register_template_filters(templates.env)
seed_interest_topics()


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

    if card_context.card_type == "conversation":
        # Auto-start a conversation card
        from .conversation import ConversationCard, ConversationEngine, ConversationMessage
        from .db import now_iso as _now_iso

        engine = ConversationEngine()
        from .conversation import get_random_topic
        topic = card_context.interest_topics[0] if card_context.interest_topics else get_random_topic()
        concept_id = card_context.concept_id
        difficulty = card_context.difficulty

        opener = engine.generate_opener(topic, concept_id, difficulty)
        timestamp = _now_iso()
        opener_msg = ConversationMessage(role="ai", content=opener, timestamp=timestamp)
        messages_json = json.dumps([opener_msg.to_dict()])

        from .db import _open_connection
        with _open_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO flow_conversations
                    (session_id, topic, messages_json, turn_count, completed, created_at, concept_id, difficulty)
                VALUES (?, ?, ?, 1, 0, ?, ?, ?)
                """,
                (session_id, topic, messages_json, timestamp, concept_id, difficulty),
            )
            conn.commit()
            conversation_id = cursor.lastrowid

        card = ConversationCard(
            topic=topic,
            concept=concept_id,
            difficulty=difficulty,
            opener=opener,
            messages=[opener_msg],
        )
        context = {
            "session_id": session_id,
            "conversation_id": conversation_id,
            "card": card,
            "concept_name": _get_concept_name(concept_id),
            "is_ended": False,
        }
        return templates.TemplateResponse(request, "partials/flow_conversation.html", context)

    # MCQ card
    concept_teach_html = _get_concept_teach_html(card_context.concept_id)
    context = {
        "session_id": session_id,
        "card_context": card_context,
        "concept_name": _get_concept_name(card_context.concept_id),
        "concept_teach_html": concept_teach_html,
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


@router.get("/flow/interests", response_class=HTMLResponse)
async def interests_dashboard(request: Request) -> Response:
    """Developer dashboard exposing interest-topic internals."""
    from .db import _open_connection

    tracker = InterestTracker()
    seed_interest_topics()
    top_topics = tracker.get_top_interests(n=25)
    now = datetime.now(timezone.utc)

    with _open_connection() as conn:
        topic_rows = conn.execute(
            """
            SELECT t.id, t.name, t.slug, t.parent_id,
                   s.score, s.interaction_count, s.last_updated, s.decay_half_life_days
            FROM interest_topics t
            LEFT JOIN user_interest_scores s ON s.topic_id = t.id
            ORDER BY COALESCE(s.score, 0) DESC, t.name
            """,
        ).fetchall()
        total_signals_row = conn.execute("SELECT COUNT(*) AS c FROM card_signals").fetchone()
        signal_rows = conn.execute(
            """
            SELECT cs.id, cs.topic_id, cs.was_correct, cs.dwell_time_ms,
                   cs.response_time_ms, cs.was_skipped, cs.concept_id, cs.card_type,
                   cs.created_at, t.name AS topic_name
            FROM card_signals cs
            LEFT JOIN interest_topics t ON t.id = cs.topic_id
            ORDER BY cs.id DESC
            LIMIT 25
            """,
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
        topics.append({
            "id": int(row["id"]),
            "name": row["name"],
            "slug": row["slug"],
            "parent_id": row["parent_id"],
            "score": raw_score,
            "decayed": decayed,
            "interaction_count": row["interaction_count"] or 0,
            "last_updated": last_updated,
        })

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


# ── Conversation card routes ─────────────────────────────────────────────────


@router.get("/flow/translate-word", response_class=HTMLResponse)
async def translate_word_endpoint(
    request: Request,
    word: str = Query(...),
    context: str = Query(""),
) -> Response:
    """Return a lightweight tooltip with a Spanish→English translation."""
    result = translate_spanish_word(word, context)
    if result is None:
        body = (
            '<div class="text-slate-400">(translation unavailable)</div>'
        )
    else:
        word_html = escape(result["word"])
        translation_html = escape(result["translation"])
        body = (
            '<div class="flex flex-col gap-1">'
            f'<div><span class="font-bold text-emerald-300">{word_html}</span>'
            '<span class="text-slate-500 mx-1">→</span>'
            f'<span class="text-slate-100">{translation_html}</span></div>'
            '</div>'
        )
    return HTMLResponse(body)


@router.post("/flow/conversation/start", response_class=HTMLResponse)
async def conversation_start(
    request: Request,
    session_id: int = Form(...),
    concept_id: str = Form(""),
    topic: str = Form(""),
    difficulty: int = Form(1),
) -> Response:
    """Start a conversation card and return the chat UI."""
    from .conversation import ConversationCard, ConversationEngine, ConversationMessage
    from .db import _open_connection, now_iso

    engine = ConversationEngine()

    # Pick concept/topic from flow context if not provided
    if not concept_id:
        card_context = select_next_card(session_id)
        concept_id = card_context.concept_id if card_context else "greetings"
        if card_context and card_context.interest_topics:
            import random
            topic = topic or random.choice(card_context.interest_topics)
    if not topic:
        from .conversation import get_random_topic
        topic = get_random_topic()

    opener = engine.generate_opener(topic, concept_id, difficulty)

    # Create conversation record in DB
    timestamp = now_iso()
    opener_msg = ConversationMessage(role="ai", content=opener, timestamp=timestamp)
    messages_json = json.dumps([opener_msg.to_dict()])

    with _open_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO flow_conversations
                (session_id, topic, messages_json, turn_count, completed, created_at, concept_id, difficulty)
            VALUES (?, ?, ?, 1, 0, ?, ?, ?)
            """,
            (session_id, topic, messages_json, timestamp, concept_id, difficulty),
        )
        conn.commit()
        conversation_id = cursor.lastrowid

    card = ConversationCard(
        topic=topic,
        concept=concept_id,
        difficulty=difficulty,
        opener=opener,
        messages=[opener_msg],
    )

    context = {
        "session_id": session_id,
        "conversation_id": conversation_id,
        "card": card,
        "concept_name": _get_concept_name(concept_id),
        "is_ended": False,
    }
    return templates.TemplateResponse(request, "partials/flow_conversation.html", context)


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
        row = conn.execute(
            "SELECT * FROM flow_conversations WHERE id = ?", (conversation_id,)
        ).fetchone()

    if row is None:
        return HTMLResponse("<p>Conversation not found.</p>", status_code=404)

    topic = str(row["topic"])
    concept_id = str(row["concept_id"] or "")
    difficulty = int(row["difficulty"])
    existing_messages = json.loads(row["messages_json"])
    messages = [ConversationMessage.from_dict(m) for m in existing_messages]
    score_was_none = row["score"] is None

    clean_message = user_message.strip()
    english_result = engine.detect_and_handle_english(
        clean_message,
        concept_id,
        difficulty,
    )

    user_text_for_engine = english_result.spanish_translation if english_result else clean_message

    # Single LLM call: evaluate + reply + steer
    result = engine.respond_to_user(
        messages=messages,
        user_text=user_text_for_engine,
        topic=topic,
        concept=concept_id,
        difficulty=difficulty,
    )

    # Add user message with corrections from the evaluation
    corrections = None if english_result else (result.corrections if result.corrections else None)
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
    )

    # End if hard cap reached OR LLM says conversation is done
    hard_cap = engine.should_end(card)
    is_ended = hard_cap or not result.should_continue

    if not is_ended:
        # Add Marta's reply
        ai_msg = ConversationMessage(role="ai", content=result.ai_reply, timestamp=now_iso())
        messages.append(ai_msg)

    # Update DB
    messages_json = json.dumps([m.to_dict() for m in messages])
    corrections_json = json.dumps([
        {
            "original": c.original,
            "corrected": c.corrected,
            "explanation": c.explanation,
            "concept_id": c.concept_id,
        }
        for m in messages if m.corrections
        for c in m.corrections
    ])

    with _open_connection() as conn:
        conn.execute(
            """
            UPDATE flow_conversations
            SET messages_json = ?, turn_count = ?, completed = ?, corrections_json = ?
            WHERE id = ?
            """,
            (messages_json, len(messages), int(is_ended), corrections_json, conversation_id),
        )
        conn.commit()

    context = {
        "session_id": session_id,
        "conversation_id": conversation_id,
        "card": card,
        "concept_name": _get_concept_name(concept_id),
        "is_ended": is_ended,
        "hint": result.hint,
    }
    return templates.TemplateResponse(request, "partials/flow_conversation.html", context)


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
        row = conn.execute(
            "SELECT * FROM flow_conversations WHERE id = ?", (conversation_id,)
        ).fetchone()

    if row is None:
        return HTMLResponse("<p>Conversation not found.</p>", status_code=404)

    try:
        topic = str(row["topic"])
        concept_id = str(row["concept_id"] or "")
        difficulty = int(row["difficulty"]) if row["difficulty"] is not None else 1
        existing_messages = json.loads(row["messages_json"])
        messages = [ConversationMessage.from_dict(m) for m in existing_messages]
        score_was_none = row["score"] is None

        card = ConversationCard(
            topic=topic,
            concept=concept_id,
            difficulty=difficulty,
            opener=messages[0].content if messages else "",
            messages=messages,
        )

        summary = engine.generate_summary(card)

        # Save score to DB
        with _open_connection() as conn:
            conn.execute(
                "UPDATE flow_conversations SET score = ?, completed = 1 WHERE id = ?",
                (summary.score, conversation_id),
            )
            conn.commit()

        if score_was_none:
            session = get_session(session_id)
            if session:
                update_session(session_id, cards_answered=session.cards_answered + 1)

        context = {
            "session_id": session_id,
            "conversation_id": conversation_id,
            "card": card,
            "summary": summary,
            "concept_name": _get_concept_name(concept_id),
            "score_pct": int(summary.score * 100),
        }
        return templates.TemplateResponse(request, "partials/flow_conversation_summary.html", context)
    except Exception as exc:
        import traceback
        traceback.print_exc()
        return HTMLResponse(
            f'<div class="rounded-2xl bg-red-500/10 p-6 ring-1 ring-red-500/30 text-center">'
            f'<p class="text-sm text-red-300 mb-3">Summary failed: {escape(str(exc))}</p>'
            f'<button hx-get="/flow/card?session_id={session_id}" hx-target="#flow-card-slot" hx-swap="innerHTML"'
            f' class="rounded-xl bg-slate-700 px-5 py-3 text-sm font-bold text-slate-200 hover:bg-slate-600">'
            f'Skip to Next Card</button></div>',
            status_code=200,
        )


@router.post("/flow/clear-mcq-cache", response_class=HTMLResponse)
async def clear_mcq_cache_endpoint(
    concept_id: str = Form(default=""),
) -> Response:
    """Clear AI-generated MCQ cache so questions regenerate with improved prompts."""
    cid = concept_id.strip() or None
    deleted = clear_mcq_cache(concept_id=cid, source="ai")
    label = f"concept '{cid}'" if cid else "all concepts"
    return HTMLResponse(f"<p>Cleared {deleted} cached MCQs for {label}. Fresh questions will generate on next play.</p>")


def _render_teach(content: str | None) -> str:
    """Convert markdown teach_content to HTML."""
    if not content:
        return ""
    return markdown.markdown(content.strip())


def _get_concept_name(concept_id: str) -> str:
    concepts = load_concepts()
    concept = concepts.get(concept_id)
    return concept.name if concept else concept_id


def _get_concept_teach_html(concept_id: str) -> str:
    concepts = load_concepts()
    concept = concepts.get(concept_id)
    if concept and concept.teach_content:
        return _render_teach(concept.teach_content)
    return ""


def _get_misconception_hint(misconception_id: str | None) -> str:
    if not misconception_id:
        return ""
    concepts = load_concepts()
    concept = concepts.get(misconception_id)
    if concept:
        return f"Review: {concept.name}"
    return ""
