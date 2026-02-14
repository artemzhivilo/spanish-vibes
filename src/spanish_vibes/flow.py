"""Core Flow Mode v2 engine: concept-based BKT scheduler, MCQ card selection."""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

from .bkt import bkt_update, is_mastered
from .concepts import get_next_new_concepts, load_concepts
from .flow_ai import ai_available
from .interest import InterestTracker
from .words import get_intro_candidate, build_practice_card, build_match_card
from .conversation_types import select_conversation_type
from .db import consume_dev_override, get_dev_override
from .flow_db import (
    create_session,
    end_session,
    get_active_session,
    get_all_concept_knowledge,
    get_cached_mcqs,
    get_concept_knowledge,
    get_last_conversation_info,
    get_or_create_flow_state,
    get_session,
    get_session_responses,
    increment_mcq_usage,
    record_response,
    update_concept_knowledge,
    update_flow_state,
    update_session,
)
from .models import ConceptKnowledge, FlowCardContext, FlowSession, MCQCard
from .srs import calculate_xp_award

# Conversation card injection: every N MCQ cards, offer a conversation
CONVERSATION_EVERY_N_CARDS = 5

# Bucket weights for card selection
WEIGHT_SPOT_CHECK = 0.30  # mastered concepts
WEIGHT_PRACTICE = 0.50    # learning concepts
WEIGHT_NEW = 0.20         # new concepts
_FORCEABLE_CARD_TYPES: tuple[str, ...] = (
    "mcq",
    "conversation",
    "story_comprehension",
    "teach",
    "word_intro",
    "word_practice",
    "word_match",
)

_USER_LEVEL_CACHE: dict[str, object] = {}


def invalidate_user_level_cache() -> None:
    """Clear computed user-level cache after mastery updates."""
    _USER_LEVEL_CACHE.clear()


def get_user_level(
    knowledge: dict[str, ConceptKnowledge] | None = None,
    concepts: dict[str, object] | None = None,
) -> dict[str, object]:
    """Compute global user level from concept mastery."""
    if knowledge is None and concepts is None:
        cached = _USER_LEVEL_CACHE.get("value")
        if isinstance(cached, dict):
            return dict(cached)

    all_knowledge = knowledge if knowledge is not None else get_all_concept_knowledge()
    all_concepts = concepts if concepts is not None else load_concepts()

    tiers: dict[int, list[str]] = {1: [], 2: [], 3: []}
    for concept_id, concept in all_concepts.items():
        level = int(getattr(concept, "difficulty_level", 1))
        tier = max(1, min(3, level))
        tiers[tier].append(concept_id)

    def _tier_mastery(tier: int) -> float:
        concept_ids = tiers.get(tier, [])
        if not concept_ids:
            return 0.0
        mastered = 0
        for concept_id in concept_ids:
            ck = all_knowledge.get(concept_id)
            if ck and is_mastered(ck.p_mastery, ck.n_attempts):
                mastered += 1
        return mastered / len(concept_ids)

    tier_mastery = {
        1: _tier_mastery(1),
        2: _tier_mastery(2),
        3: _tier_mastery(3),
    }

    t1 = tier_mastery[1]
    t2 = tier_mastery[2]
    if t1 < 0.8:
        level = 1
        cefr = "A1"
    elif t2 < 0.5:
        level = 2
        cefr = "A1-A2"
    elif t2 < 0.8:
        level = 2
        cefr = "A2"
    else:
        level = 3
        cefr = "A2-B1"

    total_mastered = sum(
        1
        for concept_id, ck in all_knowledge.items()
        if concept_id in all_concepts and is_mastered(ck.p_mastery, ck.n_attempts)
    )
    result: dict[str, object] = {
        "level": level,
        "cefr": cefr,
        "tier_mastery": tier_mastery,
        "session_difficulty": level,
        "total_mastered": total_mastered,
        "total_concepts": len(all_concepts),
    }
    if knowledge is None and concepts is None:
        _USER_LEVEL_CACHE["value"] = dict(result)
    return result


@dataclass
class FlowAnswerResult:
    is_correct: bool
    correct_answer: str
    concept_id: str
    misconception_concept: str | None
    xp_earned: int
    streak: int
    longest_streak: int
    cards_answered: int
    correct_count: int
    concepts_mastered: int
    total_concepts: int


@dataclass
class FlowSessionState:
    """In-memory session tracking (rebuilt from DB each request)."""
    session: FlowSession
    current_streak: int = 0
    recent_correct: list[bool] = field(default_factory=list)

    @property
    def cards_answered(self) -> int:
        return self.session.cards_answered


def build_session_state(session_id: int) -> FlowSessionState | None:
    """Rebuild session state from the database."""
    session = get_session(session_id)
    if session is None:
        return None

    responses = get_session_responses(session_id)
    current_streak = 0
    recent_correct: list[bool] = []

    for resp in responses:
        recent_correct.append(resp.is_correct)
        if resp.is_correct:
            current_streak += 1
        else:
            current_streak = 0

    return FlowSessionState(
        session=session,
        current_streak=current_streak,
        recent_correct=recent_correct,
    )


def start_or_resume_session() -> FlowSession:
    """Return an active session or create a new one."""
    active = get_active_session()
    if active:
        return active
    state = get_or_create_flow_state()
    flow_score = float(state["current_flow_score"])
    return create_session(flow_score)


def select_next_card(session_id: int) -> FlowCardContext | None:
    """Pick the next card for the flow session using concept-based BKT scheduling."""
    concepts = load_concepts()
    knowledge = get_all_concept_knowledge()

    # Classify concepts into buckets
    mastered_ids: list[str] = []
    learning_ids: list[str] = []

    for concept_id, ck in knowledge.items():
        if concept_id not in concepts:
            continue
        if ck.n_attempts == 0:
            continue
        if is_mastered(ck.p_mastery, ck.n_attempts):
            mastered_ids.append(concept_id)
        else:
            learning_ids.append(concept_id)

    available_new = get_next_new_concepts(knowledge, concepts, limit=3)

    forced_concept = consume_dev_override("force_next_concept")
    concept_id = forced_concept if forced_concept in concepts else None
    if concept_id is None:
        # Weighted random bucket selection
        concept_id = _pick_concept(mastered_ids, learning_ids, available_new, knowledge)
    if concept_id is None:
        return None

    # Get top interest topics for theming
    tracker = InterestTracker()
    top_interests = tracker.get_top_interests(5)
    interest_topic_names = [t.name for t in top_interests]

    forced_card_type = _consume_forced_card_type()
    if forced_card_type in {"conversation", "story_comprehension"}:
        forced_conversation_type = _consume_forced_conversation_type()
        conversation_type = (
            forced_conversation_type
            if forced_conversation_type in {"general_chat", "role_play", "concept_required", "tutor", "story_comprehension"}
            else ("story_comprehension" if forced_card_type == "story_comprehension" else "general_chat")
        )
        return _build_conversation_card_context(
            card_type=forced_card_type,
            concept_id=concept_id,
            concepts=concepts,
            interest_topic_names=interest_topic_names,
            session_id=session_id,
            knowledge=knowledge,
            learning_ids=learning_ids,
            mastered_ids=mastered_ids,
            forced_conversation_type=conversation_type,
        )

    # Conversation card injection: every N cards, offer a conversation
    # Only for learning/mastered concepts (not brand-new ones) and when AI is available
    session = get_session(session_id)
    cards_so_far = session.cards_answered if session else 0
    conversation_every_n = _get_conversation_frequency()
    ck_check = knowledge.get(concept_id)
    is_experienced = ck_check is not None and ck_check.n_attempts >= 3
    if (
        cards_so_far > 0
        and cards_so_far % conversation_every_n == 0
        and is_experienced
        and ai_available()
    ):
        forced_conversation_type = _consume_forced_conversation_type()
        return _build_conversation_card_context(
            card_type="conversation",
            concept_id=concept_id,
            concepts=concepts,
            interest_topic_names=interest_topic_names,
            session_id=session_id,
            knowledge=knowledge,
            learning_ids=learning_ids,
            mastered_ids=mastered_ids,
            forced_conversation_type=forced_conversation_type,
        )

    if forced_card_type == "teach":
        concept = concepts[concept_id]
        return FlowCardContext(
            card_type="teach",
            concept_id=concept_id,
            question="",
            correct_answer="",
            teach_content=concept.teach_content,
            interest_topics=interest_topic_names,
        )

    # For new concepts: return teach card if teach_shown == 0
    ck = knowledge.get(concept_id)
    if forced_card_type in (None, "teach") and ck is not None and ck.n_attempts == 0 and not ck.teach_shown:
        concept = concepts[concept_id]
        return FlowCardContext(
            card_type="teach",
            concept_id=concept_id,
            question="",
            correct_answer="",
            teach_content=concept.teach_content,
            interest_topics=interest_topic_names,
        )

    intro_word = get_intro_candidate(concept_id)
    if forced_card_type == "word_intro" and intro_word is None:
        forced_card_type = None
    if intro_word:
        if forced_card_type in (None, "word_intro"):
            return FlowCardContext(
                card_type="word_intro",
                concept_id=concept_id,
                question="",
                correct_answer="",
                word_id=intro_word.id,
                word_spanish=intro_word.spanish,
                word_english=intro_word.english,
                word_emoji=intro_word.emoji,
                word_sentence=intro_word.example_sentence or "",
                interest_topics=interest_topic_names,
            )

    match_card = build_match_card(concept_id)
    if match_card and (forced_card_type == "word_match" or (forced_card_type is None and random.random() < 0.4)):
        return FlowCardContext(
            card_type="word_match",
            concept_id=concept_id,
            question="Empareja las palabras",
            correct_answer="",
            options=match_card["options"],
            word_pairs=match_card["pairs"],
            interest_topics=interest_topic_names,
        )

    practice_card = build_practice_card(concept_id)
    if practice_card and forced_card_type in (None, "word_practice"):
        return FlowCardContext(
            card_type="word_practice",
            concept_id=concept_id,
            question=practice_card["prompt"],
            correct_answer=practice_card["correct_answer"],
            options=practice_card["options"],
            word_id=practice_card["word_id"],
            word_spanish=practice_card["spanish"],
            word_english=practice_card["english"],
            word_emoji=practice_card["emoji"],
            word_sentence=practice_card["sentence"],
            interest_topics=interest_topic_names,
        )

    # Fetch MCQ from cache
    mcq = _get_mcq_for_concept(concept_id)
    if mcq is None:
        # Try fallback: any concept with cached MCQs
        for fallback_id in learning_ids + mastered_ids:
            mcq = _get_mcq_for_concept(fallback_id)
            if mcq is not None:
                concept_id = fallback_id
                break

    if mcq is None:
        return None

    # Build options: correct + 3 distractors, shuffled
    options = [mcq.correct_answer]
    option_misconceptions: dict[str, str] = {}
    for d in mcq.distractors[:3]:
        text = d.get("text", "")
        if text:
            options.append(text)
            misconception = d.get("misconception", "")
            if misconception:
                option_misconceptions[text] = misconception

    random.shuffle(options)

    return FlowCardContext(
        card_type="mcq",
        concept_id=concept_id,
        question=mcq.question,
        correct_answer=mcq.correct_answer,
        options=options,
        option_misconceptions=option_misconceptions,
        difficulty=mcq.difficulty,
        mcq_card_id=mcq.id,
        interest_topics=interest_topic_names,
    )


def _pick_concept(
    mastered: list[str],
    learning: list[str],
    available_new: list[str],
    knowledge: dict[str, ConceptKnowledge],
) -> str | None:
    """Weighted random pick from concept buckets."""
    weight_spot_check, weight_practice, weight_new = _get_bucket_weights()
    buckets: list[tuple[float, list[str]]] = []
    if mastered:
        buckets.append((weight_spot_check, mastered))
    if learning:
        buckets.append((weight_practice, learning))
    if available_new:
        buckets.append((weight_new, available_new))

    if not buckets:
        return None

    # Normalize weights
    total_weight = sum(w for w, _ in buckets)
    roll = random.random() * total_weight
    cumulative = 0.0
    chosen_bucket: list[str] = buckets[0][1]
    for weight, bucket in buckets:
        cumulative += weight
        if roll <= cumulative:
            chosen_bucket = bucket
            break

    # Within practice bucket, prefer lowest p_mastery
    if chosen_bucket is learning and len(chosen_bucket) > 1:
        chosen_bucket.sort(key=lambda cid: knowledge.get(cid, ConceptKnowledge(
            concept_id=cid, p_mastery=0.0, n_attempts=0, n_correct=0,
            n_wrong=0, teach_shown=False, last_seen_at=None,
        )).p_mastery)
        # Pick from bottom half with some randomness
        half = max(1, len(chosen_bucket) // 2)
        return random.choice(chosen_bucket[:half])

    return random.choice(chosen_bucket)


def _get_bucket_weights() -> tuple[float, float, float]:
    def _override(name: str, default: float) -> float:
        value = get_dev_override(name)
        if value is None:
            return default
        try:
            parsed = float(value)
        except ValueError:
            return default
        return max(0.0, parsed)

    spot = _override("bucket_weight_spot_check", WEIGHT_SPOT_CHECK)
    practice = _override("bucket_weight_practice", WEIGHT_PRACTICE)
    new = _override("bucket_weight_new", WEIGHT_NEW)
    total = spot + practice + new
    if total <= 0:
        return WEIGHT_SPOT_CHECK, WEIGHT_PRACTICE, WEIGHT_NEW
    return spot / total, practice / total, new / total


def _get_conversation_frequency() -> int:
    value = get_dev_override("conversation_frequency")
    if value is None:
        return CONVERSATION_EVERY_N_CARDS
    try:
        parsed = int(value)
    except ValueError:
        return CONVERSATION_EVERY_N_CARDS
    return max(1, min(50, parsed))


def _consume_forced_card_type() -> str | None:
    value = consume_dev_override("force_next_card_type")
    if value is None:
        return None
    normalized = value.strip().lower()
    return normalized if normalized in _FORCEABLE_CARD_TYPES else None


def _consume_forced_conversation_type() -> str | None:
    value = consume_dev_override("force_next_conversation_type")
    if value is None:
        return None
    normalized = value.strip().lower()
    valid = {"general_chat", "role_play", "concept_required", "tutor", "story_comprehension"}
    return normalized if normalized in valid else None


def _build_conversation_card_context(
    *,
    card_type: Literal["conversation", "story_comprehension"],
    concept_id: str,
    concepts: dict,
    interest_topic_names: list[str],
    session_id: int,
    knowledge: dict[str, ConceptKnowledge],
    learning_ids: list[str],
    mastered_ids: list[str],
    forced_conversation_type: str | None = None,
) -> FlowCardContext:
    # Avoid repeating the previous concept when possible.
    last_conv = get_last_conversation_info(session_id)
    last_concept = last_conv["concept_id"] if last_conv else None

    conv_concept_id = concept_id
    conv_candidates = [
        c for c in learning_ids
        if c != last_concept and knowledge.get(
            c,
            ConceptKnowledge(
                concept_id=c,
                p_mastery=0.0,
                n_attempts=0,
                n_correct=0,
                n_wrong=0,
                teach_shown=False,
                last_seen_at=None,
            ),
        ).n_attempts >= 3
    ]
    if not conv_candidates:
        conv_candidates = [c for c in mastered_ids if c != last_concept]
    if conv_candidates:
        conv_concept_id = random.choice(conv_candidates)

    if forced_conversation_type:
        conversation_type = forced_conversation_type
        target_concept_id = conv_concept_id if forced_conversation_type in {"concept_required", "tutor"} else None
    else:
        conversation_type, target_concept_id = select_conversation_type(conv_concept_id, session_id)

    effective_concept_id = target_concept_id or conv_concept_id
    selected_card_type = "story_comprehension" if conversation_type == "story_comprehension" else card_type
    if selected_card_type == "story_comprehension":
        card_kind = "story_comprehension"
    else:
        card_kind = "conversation"

    return FlowCardContext(
        card_type=card_kind,
        concept_id=effective_concept_id,
        question="",
        correct_answer="",
        interest_topics=interest_topic_names,
        difficulty=min(3, max(1, concepts[effective_concept_id].difficulty_level)),
        conversation_type=conversation_type,
        target_concept_id=target_concept_id,
    )


def _get_mcq_for_concept(concept_id: str) -> MCQCard | None:
    """Get a least-used MCQ card for the concept."""
    user_level = get_user_level()
    preferred_difficulty = int(user_level.get("session_difficulty", 1))
    mcqs = get_cached_mcqs(
        concept_id,
        limit=1,
        preferred_difficulty=preferred_difficulty,
    )
    return mcqs[0] if mcqs else None


def process_mcq_answer(
    *,
    session_id: int,
    card_context: FlowCardContext,
    chosen_option: str,
    response_time_ms: int | None = None,
    count_card: bool = True,
) -> FlowAnswerResult:
    """Process an MCQ tap: grade, BKT update, record, return result."""
    state = build_session_state(session_id)
    if state is None:
        raise ValueError(f"Session {session_id} not found")

    is_correct = chosen_option == card_context.correct_answer
    concept_id = card_context.concept_id

    # BKT update on target concept
    ck = get_concept_knowledge(concept_id)
    if ck is not None:
        new_p = bkt_update(ck.p_mastery, is_correct)
        update_concept_knowledge(concept_id, new_p, is_correct)

    # Misconception penalty
    misconception_concept: str | None = None
    if not is_correct:
        misconception_concept = card_context.option_misconceptions.get(chosen_option)
        if misconception_concept:
            mc_ck = get_concept_knowledge(misconception_concept)
            if mc_ck is not None:
                # Small penalty: treat as wrong answer with lower transit
                new_mc_p = bkt_update(mc_ck.p_mastery, False, p_transit=0.05)
                update_concept_knowledge(misconception_concept, new_mc_p, False)

    # Increment MCQ usage
    if card_context.mcq_card_id is not None:
        increment_mcq_usage(card_context.mcq_card_id)

    # Streak
    new_streak = (state.current_streak + 1) if is_correct else 0
    longest_streak = max(state.session.longest_streak, new_streak)

    # XP
    xp_earned = 0
    if is_correct:
        xp_earned = calculate_xp_award(state.current_streak)
        from .db import add_xp, record_practice_today
        add_xp(xp_earned)
        record_practice_today(datetime.now(timezone.utc).strftime("%Y-%m-%d"))

    # Record response
    cards_answered = state.session.cards_answered + (1 if count_card else 0)
    correct_count = state.session.correct_count + (1 if is_correct else 0)
    total_xp = state.session.xp_earned + xp_earned

    record_response(
        session_id=session_id,
        card_id=None,
        response_type="mcq",
        prompt_json=json.dumps({"question": card_context.question, "concept_id": concept_id}),
        user_answer=chosen_option,
        expected_answer=card_context.correct_answer,
        is_correct=is_correct,
        response_time_ms=response_time_ms,
        difficulty_score=float(card_context.difficulty),
        flow_score_after=state.session.flow_score,
        concept_id=concept_id,
        chosen_option=chosen_option,
        misconception_concept=misconception_concept,
    )

    # Update session
    update_session(
        session_id,
        cards_answered=cards_answered,
        correct_count=correct_count,
        xp_earned=total_xp,
        longest_streak=longest_streak,
    )

    # Update flow state
    update_flow_state(total_cards_increment=(1 if count_card else 0))

    # Count mastered concepts
    concepts = load_concepts()
    all_knowledge = get_all_concept_knowledge()
    concepts_mastered = sum(
        1 for cid, ck in all_knowledge.items()
        if cid in concepts and is_mastered(ck.p_mastery, ck.n_attempts)
    )

    return FlowAnswerResult(
        is_correct=is_correct,
        correct_answer=card_context.correct_answer,
        concept_id=concept_id,
        misconception_concept=misconception_concept,
        xp_earned=xp_earned,
        streak=new_streak,
        longest_streak=longest_streak,
        cards_answered=cards_answered,
        correct_count=correct_count,
        concepts_mastered=concepts_mastered,
        total_concepts=len(concepts),
    )


def end_flow_session(session_id: int) -> FlowSession | None:
    """End a flow session and update global state."""
    session = end_session(session_id)
    if session:
        update_flow_state(total_sessions_increment=1)
    return session
