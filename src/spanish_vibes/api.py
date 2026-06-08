"""JSON API routes for the SvelteKit frontend.

Mirrors the flow routes but returns JSON instead of HTML partials.
Mounted under /api/ prefix.
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Query
from pydantic import BaseModel

from .bkt import is_mastered
from .concepts import load_concepts
from .db import (
    get_all_interest_topics,
    get_current_user_id,
    is_user_onboarded,
    set_dev_override,
    set_user_onboarded,
)
from .flow import (
    FlowCardContext,
    build_session_state,
    get_user_level,
    invalidate_user_level_cache,
    process_mcq_answer,
    select_next_card,
    start_or_resume_session,
)
from .flow_ai import prefetch_next_concepts
from .flow_db import (
    get_all_concept_knowledge,
    mark_teach_shown,
    update_concept_knowledge,
)
from .interest import CardSignal, InterestTracker, seed_interest_scores
from .personas import load_persona, select_persona
from .words import mark_word_practice_result

router = APIRouter(prefix="/api")


def _count_mastered() -> tuple[int, int]:
    concepts = load_concepts()
    knowledge = get_all_concept_knowledge()
    mastered = sum(
        1
        for cid, ck in knowledge.items()
        if cid in concepts and is_mastered(ck.p_mastery, ck.n_attempts)
    )
    return mastered, len(concepts)


def _card_context_to_dict(cc: FlowCardContext) -> dict[str, Any]:
    return {
        "card_type": cc.card_type,
        "concept_id": cc.concept_id,
        "question": cc.question,
        "correct_answer": cc.correct_answer,
        "options": cc.options,
        "option_misconceptions": cc.option_misconceptions,
        "difficulty": cc.difficulty,
        "mcq_card_id": cc.mcq_card_id,
        "teach_content": cc.teach_content,
        "interest_topics": cc.interest_topics,
        "word_id": cc.word_id,
        "word_spanish": cc.word_spanish,
        "word_english": cc.word_english,
        "word_emoji": cc.word_emoji,
        "word_sentence": cc.word_sentence,
        "word_pairs": cc.word_pairs,
        "scrambled_words": cc.scrambled_words,
        "correct_sentence": cc.correct_sentence,
        "english_prompt": cc.english_prompt,
        "conversation_type": cc.conversation_type,
        "target_concept_id": cc.target_concept_id,
    }


# ── Session & Progress ──────────────────────────────────────────


@router.get("/progress")
def api_progress():
    """Current user progress: level, XP, streak, mastery."""
    from .app import _get_player_progress

    progress = _get_player_progress()
    mastered, total = _count_mastered()
    concepts = load_concepts()
    knowledge = get_all_concept_knowledge()
    user_level = get_user_level(knowledge, concepts)

    return {
        "progress": {
            "xp": progress.xp if progress else 0,
            "level": progress.level if progress else 1,
            "level_pct": progress.level_pct if progress else 0,
            "xp_into_level": progress.xp_into_level if progress else 0,
            "xp_for_next_level": progress.xp_for_next_level if progress else 100,
            "streak": progress.streak if progress else 0,
        }
        if progress
        else None,
        "concepts_mastered": mastered,
        "total_concepts": total,
        "cefr": user_level["cefr"],
        "user_level": user_level["level"],
        "tier_mastery": user_level["tier_mastery"],
        "onboarded": is_user_onboarded(),
    }


@router.post("/flow/session")
def api_start_session():
    """Start or resume a flow session."""
    session = start_or_resume_session()
    state = build_session_state(session.id)
    mastered, total = _count_mastered()
    concepts = load_concepts()
    knowledge = get_all_concept_knowledge()
    user_level = get_user_level(knowledge, concepts)

    return {
        "session_id": session.id,
        "cards_answered": session.cards_answered,
        "correct_count": session.correct_count,
        "streak": state.current_streak if state else 0,
        "concepts_mastered": mastered,
        "total_concepts": total,
        "cefr": user_level["cefr"],
    }


# ── Cards ────────────────────────────────────────────────────────


@router.get("/flow/card")
async def api_flow_card(
    session_id: int = Query(...),
    retry: int = Query(0),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    """Get next card as JSON."""
    card_context = select_next_card(session_id)

    if card_context is None:
        if retry < 3:
            return {"status": "loading", "retry": retry + 1}
        return {"status": "empty"}

    background_tasks.add_task(prefetch_next_concepts)

    concept_name = ""
    concepts = load_concepts()
    if card_context.concept_id in concepts:
        concept_name = concepts[card_context.concept_id].name

    return {
        "status": "ok",
        "card": _card_context_to_dict(card_context),
        "concept_name": concept_name,
        "session_id": session_id,
    }


class AnswerBody(BaseModel):
    session_id: int
    chosen_option: str = ""
    card_data: dict[str, Any] = {}
    start_time: int = 0


@router.post("/flow/answer")
async def api_flow_answer(
    body: AnswerBody,
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    """Submit answer, get feedback as JSON."""
    now_ms = int(time.time() * 1000)
    response_time_ms = (now_ms - body.start_time) if body.start_time > 0 else None

    card_context = FlowCardContext(
        card_type=body.card_data.get("card_type", "mcq"),
        concept_id=body.card_data.get("concept_id", ""),
        question=body.card_data.get("question", ""),
        correct_answer=body.card_data.get("correct_answer", ""),
        options=body.card_data.get("options", []),
        option_misconceptions=body.card_data.get("option_misconceptions", {}),
        difficulty=int(body.card_data.get("difficulty", 1)),
        mcq_card_id=body.card_data.get("mcq_card_id"),
        word_id=body.card_data.get("word_id"),
        word_spanish=body.card_data.get("word_spanish", ""),
        word_emoji=body.card_data.get("word_emoji"),
        word_english=body.card_data.get("word_english", ""),
        word_sentence=body.card_data.get("word_sentence", ""),
        scrambled_words=body.card_data.get("scrambled_words", []),
        correct_sentence=body.card_data.get("correct_sentence", ""),
        english_prompt=body.card_data.get("english_prompt", ""),
    )

    result = process_mcq_answer(
        session_id=body.session_id,
        card_context=card_context,
        chosen_option=body.chosen_option,
        response_time_ms=response_time_ms,
    )

    if (
        card_context.card_type in {"word_practice", "emoji_association"}
        and card_context.word_id
    ):
        mark_word_practice_result(card_context.word_id, result.is_correct)

    signal = CardSignal(
        topic_id=None,
        was_correct=result.is_correct,
        dwell_time_ms=response_time_ms,
        response_time_ms=response_time_ms,
        card_id=card_context.mcq_card_id,
        session_id=body.session_id,
        concept_id=card_context.concept_id,
        card_type=card_context.card_type,
    )
    InterestTracker().update_from_card_signal(signal)
    background_tasks.add_task(prefetch_next_concepts)

    concept_name = ""
    concepts = load_concepts()
    if result.concept_id in concepts:
        concept_name = concepts[result.concept_id].name

    return {
        "is_correct": result.is_correct,
        "correct_answer": result.correct_answer,
        "concept_id": result.concept_id,
        "concept_name": concept_name,
        "xp_earned": result.xp_earned,
        "streak": result.streak,
        "cards_answered": result.cards_answered,
        "concepts_mastered": result.concepts_mastered,
        "total_concepts": result.total_concepts,
        "misconception_concept": result.misconception_concept,
    }


@router.post("/flow/teach-seen")
async def api_teach_seen(
    session_id: int = Query(...),
    concept_id: str = Query(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    """Mark teach card as seen, return next card."""
    mark_teach_shown(concept_id)
    update_concept_knowledge(concept_id, 0.3, True)
    background_tasks.add_task(prefetch_next_concepts)
    return {"ok": True}


# ── Onboarding ───────────────────────────────────────────────────


@router.get("/onboarding")
def api_onboarding():
    """Onboarding state and available topics/tiers."""
    if is_user_onboarded():
        return {"onboarded": True}

    topics = get_all_interest_topics()
    concepts = load_concepts()
    tiers: dict[int, list[dict[str, str]]] = {}
    for concept_id, concept in sorted(
        concepts.items(), key=lambda item: (item[1].difficulty_level, item[1].name)
    ):
        tiers.setdefault(concept.difficulty_level, []).append(
            {"id": concept_id, "name": concept.name}
        )

    return {
        "onboarded": False,
        "topics": [{"id": t["id"], "name": t["name"]} for t in topics],
        "tiers": [
            {"tier": tier, "concepts": entries}
            for tier, entries in sorted(tiers.items())
        ],
    }


class OnboardingBody(BaseModel):
    start_tier: int = 1
    interest_topic_ids: list[int] = []


@router.post("/onboarding/complete")
def api_complete_onboarding(body: OnboardingBody):
    """Complete onboarding with tier selection."""
    if is_user_onboarded():
        return {"ok": True}

    if body.interest_topic_ids:
        try:
            seed_interest_scores(body.interest_topic_ids, initial_score=0.35)
        except Exception:
            pass

    concepts = load_concepts()
    if not concepts:
        set_user_onboarded(True)
        return {"ok": True}

    max_tier = max(c.difficulty_level for c in concepts.values())
    tier = max(1, min(max_tier, int(body.start_tier)))

    for concept_id, concept in concepts.items():
        if concept.difficulty_level < tier:
            mark_teach_shown(concept_id)
            update_concept_knowledge(concept_id, 0.95, True)

    invalidate_user_level_cache()

    tier_concepts = sorted(
        [cid for cid, concept in concepts.items() if concept.difficulty_level == tier],
        key=lambda cid: concepts[cid].name,
    )
    if tier_concepts:
        set_dev_override("force_next_concept", tier_concepts[0])

    from .flow_db import get_active_session, end_session

    active = get_active_session()
    if active:
        end_session(active.id)

    set_user_onboarded(True)
    return {"ok": True}


# ── Concepts / Stats / Words ────────────────────────────────────


@router.get("/concepts")
def api_concepts():
    """All concepts with mastery status."""
    concepts = load_concepts()
    knowledge = get_all_concept_knowledge()

    result = []
    for concept_id, concept in sorted(
        concepts.items(), key=lambda x: (x[1].difficulty_level, x[1].name)
    ):
        ck = knowledge.get(concept_id)
        result.append(
            {
                "id": concept_id,
                "name": concept.name,
                "description": concept.description,
                "difficulty_level": concept.difficulty_level,
                "mastery": round(ck.p_mastery, 2) if ck else 0.0,
                "attempts": ck.n_attempts if ck else 0,
                "correct": ck.n_correct if ck else 0,
                "is_mastered": is_mastered(ck.p_mastery, ck.n_attempts)
                if ck
                else False,
                "teach_shown": ck.teach_shown if ck else False,
            }
        )
    return {"concepts": result}


@router.get("/stats")
def api_stats():
    """Learning stats summary."""
    from .app import _get_player_progress

    progress = _get_player_progress()
    mastered, total = _count_mastered()
    concepts = load_concepts()
    knowledge = get_all_concept_knowledge()
    user_level = get_user_level(knowledge, concepts)

    tiers: dict[int, dict[str, Any]] = {}
    for concept_id, concept in concepts.items():
        tier = concept.difficulty_level
        if tier not in tiers:
            tiers[tier] = {"total": 0, "mastered": 0, "concepts": []}
        tiers[tier]["total"] += 1
        ck = knowledge.get(concept_id)
        mastered_flag = is_mastered(ck.p_mastery, ck.n_attempts) if ck else False
        if mastered_flag:
            tiers[tier]["mastered"] += 1
        tiers[tier]["concepts"].append(
            {
                "id": concept_id,
                "name": concept.name,
                "mastery": round(ck.p_mastery, 2) if ck else 0.0,
                "is_mastered": mastered_flag,
            }
        )

    return {
        "progress": {
            "xp": progress.xp if progress else 0,
            "level": progress.level if progress else 1,
            "streak": progress.streak if progress else 0,
        }
        if progress
        else None,
        "concepts_mastered": mastered,
        "total_concepts": total,
        "cefr": user_level["cefr"],
        "tiers": {str(k): v for k, v in sorted(tiers.items())},
    }


@router.get("/words")
def api_words():
    """Vocabulary list with practice state."""
    from .db import _open_connection

    uid = get_current_user_id()
    with _open_connection() as conn:
        rows = conn.execute(
            """SELECT id, spanish, english, emoji, concept_id, status,
                      times_seen, times_correct
               FROM words WHERE user_id = ? ORDER BY spanish""",
            (uid,),
        ).fetchall()

    return {
        "words": [
            {
                "id": r["id"],
                "spanish": r["spanish"],
                "english": r["english"],
                "emoji": r["emoji"],
                "concept_id": r["concept_id"],
                "status": r["status"],
                "times_seen": r["times_seen"],
                "times_correct": r["times_correct"],
            }
            for r in rows
        ]
    }


# ── Conversations ───────────────────────────────────────────────


class ConversationStartBody(BaseModel):
    session_id: int
    concept_id: str = ""
    topic: str = ""
    difficulty: int = 1
    conversation_type: str = ""


@router.post("/flow/conversation/start")
def api_conversation_start(body: ConversationStartBody):
    """Start a conversation and return opener + metadata."""
    import json

    from .conversation import ConversationEngine, ConversationMessage
    from .conversation_types import get_type_instruction, select_conversation_type
    from .db import _open_connection, consume_dev_override, now_iso
    from .flow_db import get_last_conversation_info

    engine = ConversationEngine()

    concept_id = body.concept_id or "greetings"
    topic = body.topic
    if not topic:
        from .conversation import get_random_topic

        topic = get_random_topic()

    if body.conversation_type:
        selected_type = body.conversation_type
        target_concept_id = concept_id
    else:
        forced = consume_dev_override("force_next_conversation_type")
        if forced:
            selected_type = forced
            target_concept_id = concept_id
        else:
            selected_type, target_concept_id = select_conversation_type(
                concept_id, body.session_id
            )
    effective_concept_id = target_concept_id or concept_id

    from .flow_routes import (
        _build_conversation_guardrails,
        _compose_persona_prompt,
        _get_seen_and_mastered_concepts,
    )

    seen_concepts, mastered_concepts = _get_seen_and_mastered_concepts()
    last_conv = get_last_conversation_info(body.session_id)
    exclude_persona_id = last_conv.get("persona_id") if last_conv else None
    persona = select_persona(
        exclude_id=exclude_persona_id,
        difficulty=body.difficulty,
        seen_concepts=seen_concepts,
        mastered_concepts=mastered_concepts,
    )
    type_instruction = get_type_instruction(
        selected_type,
        concept_id=effective_concept_id,
        topic=topic,
        persona_id=persona.id,
    )
    persona_prompt = _compose_persona_prompt(persona, type_instruction=type_instruction)
    user_level_info = get_user_level()
    effective_difficulty = int(
        user_level_info.get("session_difficulty", body.difficulty)
    )
    conversation_guardrails = _build_conversation_guardrails(
        concept_id=effective_concept_id,
        difficulty=effective_difficulty,
        seen_concepts=seen_concepts,
        mastered_concepts=mastered_concepts,
    )

    opener = engine.generate_opener(
        topic,
        effective_concept_id,
        effective_difficulty,
        persona_prompt=persona_prompt,
        persona_name=persona.name,
        conversation_guardrails=conversation_guardrails,
    )

    timestamp = now_iso()
    opener_msg = ConversationMessage(role="ai", content=opener, timestamp=timestamp)
    messages_json = json.dumps([opener_msg.to_dict()])

    uid = get_current_user_id()
    with _open_connection() as conn:
        cursor = conn.execute(
            """INSERT INTO flow_conversations
                (user_id, session_id, topic, messages_json, turn_count,
                 completed, created_at, concept_id, difficulty,
                 persona_id, conversation_type)
            VALUES (?, ?, ?, ?, 1, 0, ?, ?, ?, ?, ?)""",
            (
                uid,
                body.session_id,
                topic,
                messages_json,
                timestamp,
                effective_concept_id,
                effective_difficulty,
                persona.id,
                selected_type,
            ),
        )
        conn.commit()
        conversation_id = int(cursor.lastrowid)

    return {
        "conversation_id": conversation_id,
        "persona_id": persona.id,
        "persona_name": persona.name,
        "topic": topic,
        "concept_id": effective_concept_id,
        "conversation_type": selected_type,
        "messages": [
            {"role": "ai", "content": opener},
        ],
    }


class ConversationRespondBody(BaseModel):
    session_id: int
    conversation_id: int
    message: str


@router.post("/flow/conversation/respond")
def api_conversation_respond(body: ConversationRespondBody):
    """Send a message, get tutor response + corrections."""
    import json

    from .conversation import (
        ConversationCard,
        ConversationEngine,
        ConversationMessage,
    )
    from .conversation_types import get_type_instruction
    from .db import _open_connection, now_iso
    from .flow_routes import _build_conversation_guardrails, _compose_persona_prompt

    engine = ConversationEngine()
    timestamp = now_iso()
    uid = get_current_user_id()

    with _open_connection() as conn:
        row = conn.execute(
            "SELECT * FROM flow_conversations WHERE user_id = ? AND id = ?",
            (uid, body.conversation_id),
        ).fetchone()

    if row is None:
        return {"error": "Conversation not found"}

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
    )
    persona_prompt = _compose_persona_prompt(persona, type_instruction=type_instruction)
    existing_messages = json.loads(row["messages_json"])
    messages = [ConversationMessage.from_dict(m) for m in existing_messages]

    clean_message = body.message.strip()
    english_result = engine.detect_and_handle_english(
        clean_message, concept_id, difficulty
    )
    user_text = english_result.spanish_translation if english_result else clean_message

    conversation_guardrails = _build_conversation_guardrails(
        concept_id=concept_id, difficulty=difficulty
    )
    result = engine.respond_to_user(
        messages=messages,
        user_text=user_text,
        topic=topic,
        concept=concept_id,
        difficulty=difficulty,
        persona_prompt=persona_prompt,
        persona_name=persona.name,
        conversation_guardrails=conversation_guardrails,
    )

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

    translation_info = None
    if english_result:
        system_msg = ConversationMessage(
            role="system",
            content=english_result.display_message,
            timestamp=timestamp,
        )
        messages.append(system_msg)
        translation_info = {
            "display_message": english_result.display_message,
            "spanish_translation": english_result.spanish_translation,
            "original_english": english_result.original_english,
        }

    card = ConversationCard(
        topic=topic,
        concept=concept_id,
        difficulty=difficulty,
        opener=messages[0].content if messages else "",
        messages=messages,
        max_turns=4,
        persona_name=persona.name,
    )

    hard_cap = engine.should_end(card)
    is_ended = hard_cap or not result.should_continue

    if not is_ended:
        ai_msg = ConversationMessage(
            role="ai", content=result.ai_reply, timestamp=now_iso()
        )
        messages.append(ai_msg)

    messages_json = json.dumps([m.to_dict() for m in messages])
    with _open_connection() as conn:
        conn.execute(
            """UPDATE flow_conversations
            SET messages_json = ?, turn_count = ?, completed = ?
            WHERE user_id = ? AND id = ?""",
            (messages_json, len(messages), int(is_ended), uid, body.conversation_id),
        )
        conn.commit()

    corrections_out = []
    if corrections:
        corrections_out = [
            {
                "original": c.original,
                "corrected": c.corrected,
                "explanation": c.explanation,
            }
            for c in corrections
        ]

    return {
        "ai_reply": result.ai_reply if not is_ended else None,
        "is_ended": is_ended,
        "corrections": corrections_out,
        "hint": result.hint,
        "translation": translation_info,
        "persona_name": persona.name,
    }


@router.post("/flow/conversation/skip")
def api_conversation_skip(
    session_id: int = Query(...), conversation_id: int = Query(...)
):
    """Skip/end a conversation."""
    from .db import _open_connection

    uid = get_current_user_id()
    with _open_connection() as conn:
        conn.execute(
            "UPDATE flow_conversations SET completed = 1 WHERE user_id = ? AND id = ?",
            (uid, conversation_id),
        )
        conn.commit()
    return {"ok": True}
