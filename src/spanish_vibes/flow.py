"""Core Flow Mode v2 engine: concept-based BKT scheduler, MCQ card selection."""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .bkt import bkt_update, is_mastered
from .concepts import get_next_new_concepts, load_concepts
from .flow_ai import ai_available
from .interest import InterestTracker

# Conversation card injection: every N MCQ cards, offer a conversation
CONVERSATION_EVERY_N_CARDS = 5
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
    mark_teach_shown,
    record_response,
    update_concept_knowledge,
    update_flow_state,
    update_session,
)
from .models import ConceptKnowledge, FlowCardContext, FlowSession, MCQCard
from .srs import calculate_xp_award

# Bucket weights for card selection
WEIGHT_SPOT_CHECK = 0.30  # mastered concepts
WEIGHT_PRACTICE = 0.50    # learning concepts
WEIGHT_NEW = 0.20         # new concepts


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

    # Weighted random bucket selection
    concept_id = _pick_concept(mastered_ids, learning_ids, available_new, knowledge)
    if concept_id is None:
        return None

    # Get top interest topics for theming
    tracker = InterestTracker()
    top_interests = tracker.get_top_interests(5)
    interest_topic_names = [t.name for t in top_interests]

    # Pick a topic for theming (random from top 3, or None)
    chosen_topic: str | None = None
    if top_interests:
        chosen_topic = random.choice([t.name for t in top_interests[:3]])

    # Conversation card injection: every N cards, offer a conversation
    # Only for learning/mastered concepts (not brand-new ones) and when AI is available
    session = get_session(session_id)
    cards_so_far = session.cards_answered if session else 0
    ck_check = knowledge.get(concept_id)
    is_experienced = ck_check is not None and ck_check.n_attempts >= 3
    if (
        cards_so_far > 0
        and cards_so_far % CONVERSATION_EVERY_N_CARDS == 0
        and is_experienced
        and ai_available()
    ):
        from .conversation import get_random_topic

        # Avoid repeating the last conversation's topic and concept
        last_conv = get_last_conversation_info(session_id)
        last_topic = last_conv["topic"] if last_conv else None
        last_concept = last_conv["concept_id"] if last_conv else None

        # Prefer a different concept: pick from learning over mastered
        conv_concept_id = concept_id
        conv_candidates = [c for c in learning_ids if c != last_concept and knowledge.get(c, ConceptKnowledge(
            concept_id=c, p_mastery=0.0, n_attempts=0, n_correct=0, n_wrong=0, teach_shown=False, last_seen_at=None,
        )).n_attempts >= 3]
        if not conv_candidates:
            conv_candidates = [c for c in mastered_ids if c != last_concept]
        if conv_candidates:
            conv_concept_id = random.choice(conv_candidates)

        topic = chosen_topic or get_random_topic(exclude=last_topic)
        return FlowCardContext(
            card_type="conversation",
            concept_id=conv_concept_id,
            question="",
            correct_answer="",
            interest_topics=interest_topic_names,
            difficulty=min(3, max(1, concepts[conv_concept_id].difficulty_level)),
        )

    # For new concepts: return teach card if teach_shown == 0
    ck = knowledge.get(concept_id)
    if ck is not None and ck.n_attempts == 0 and not ck.teach_shown:
        concept = concepts[concept_id]
        return FlowCardContext(
            card_type="teach",
            concept_id=concept_id,
            question="",
            correct_answer="",
            teach_content=concept.teach_content,
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
    buckets: list[tuple[float, list[str]]] = []
    if mastered:
        buckets.append((WEIGHT_SPOT_CHECK, mastered))
    if learning:
        buckets.append((WEIGHT_PRACTICE, learning))
    if available_new:
        buckets.append((WEIGHT_NEW, available_new))

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


def _get_mcq_for_concept(concept_id: str) -> MCQCard | None:
    """Get a least-used MCQ card for the concept."""
    mcqs = get_cached_mcqs(concept_id, limit=1)
    return mcqs[0] if mcqs else None


def process_mcq_answer(
    *,
    session_id: int,
    card_context: FlowCardContext,
    chosen_option: str,
    response_time_ms: int | None = None,
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
    cards_answered = state.session.cards_answered + 1
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
    update_flow_state(total_cards_increment=1)

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
