from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Literal, NotRequired, Tuple, TypedDict, cast

CardKind = Literal["vocab", "fillblank", "verbs"]
CardDirection = Literal["es_to_en", "en_to_es"]

CARD_KINDS: tuple[CardKind, ...] = ("vocab", "fillblank", "verbs")
CARD_DIRECTIONS: tuple[CardDirection, ...] = ("es_to_en", "en_to_es")


class LessonVocabularyEntry(TypedDict):
    spanish: str
    english: str
    ex_es: NotRequired[str]
    ex_en: NotRequired[str]


class LessonFillBlankEntry(TypedDict):
    spanish: str
    solution: str
    english: str


class LessonConceptExample(TypedDict):
    text: str
    english: str


class LessonConcept(TypedDict):
    kind: str
    id: str
    examples: list[LessonConceptExample]


class LessonExerciseFeedback(TypedDict, total=False):
    correct: str
    incorrect: str


class LessonExercise(TypedDict, total=False):
    type: str
    prompt: str
    answer: str
    options: list[str]
    expected_keys: list[str]
    feedback: LessonExerciseFeedback


class CardRecord(TypedDict):
    deck_id: int
    lesson_id: int
    kind: CardKind
    prompt: str
    solution: str
    content_key: str
    direction: NotRequired[CardDirection | None]
    extra_json: NotRequired[str]
    ease: NotRequired[float]
    interval: NotRequired[int]
    reps: NotRequired[int]
    due_at: NotRequired[str]
    created_at: NotRequired[str]
    updated_at: NotRequired[str]
    concept_id: NotRequired[str | None]
    variant_id: NotRequired[str | None]


@dataclass(slots=True)
class LessonDoc:
    slug: str
    title: str
    level_score: int
    difficulty: str
    vocabulary: list[LessonVocabularyEntry] = field(default_factory=list)
    fillblanks: list[LessonFillBlankEntry] = field(default_factory=list)
    concepts: list[LessonConcept] = field(default_factory=list)
    exercises: list[LessonExercise] = field(default_factory=list)


@dataclass(slots=True)
class DeckSummary:
    id: int
    lesson_id: int
    name: str
    kind: CardKind
    card_count: int
    due_count: int


@dataclass(slots=True)
class LessonDeckSummary:
    id: int
    slug: str
    title: str
    level_score: int
    difficulty: str
    total_cards: int
    due_cards: int
    decks: list[DeckSummary]


@dataclass(slots=True)
class CardDetail:
    id: int
    deck_id: int
    lesson_id: int
    kind: CardKind
    prompt: str
    solution: str
    direction: CardDirection | None
    extra: dict[str, Any]
    ease: float
    interval: int
    reps: int
    due_at: str
    created_at: str
    updated_at: str
    concept_id: str | None
    variant_id: str | None


@dataclass(slots=True)
class LessonInfo:
    id: int
    slug: str
    title: str
    level_score: int
    difficulty: str


@dataclass(slots=True)
class PlayerProgress:
    xp: int
    level: int
    xp_into_level: int
    xp_for_next_level: int
    level_pct: int
    streak: int
    streak_last_date: str


@dataclass(slots=True)
class FlowSession:
    id: int
    started_at: str
    ended_at: str | None
    cards_answered: int
    correct_count: int
    flow_score: float
    xp_earned: int
    longest_streak: int
    status: str


@dataclass(slots=True)
class FlowResponse:
    id: int
    session_id: int
    card_id: int | None
    response_type: str
    prompt_json: str
    user_answer: str
    expected_answer: str
    is_correct: bool
    response_time_ms: int | None
    difficulty_score: float
    flow_score_after: float
    created_at: str


@dataclass(slots=True)
class FlowCardContext:
    """Card + metadata for rendering in flow mode (MCQ-based)."""
    card_type: str  # 'mcq' | 'teach' | 'conversation' | 'story_comprehension' | 'word_intro' | 'word_practice'
    concept_id: str
    question: str
    correct_answer: str
    options: list[str] = field(default_factory=list)
    option_misconceptions: dict[str, str] = field(default_factory=dict)
    difficulty: int = 1
    mcq_card_id: int | None = None
    teach_content: str = ""
    interest_topics: list[str] = field(default_factory=list)
    word_id: int | None = None
    word_spanish: str = ""
    word_english: str = ""
    word_emoji: str | None = None
    word_sentence: str = ""
    word_pairs: list[dict[str, str]] = field(default_factory=list)
    conversation_type: str = "general_chat"
    target_concept_id: str | None = None


@dataclass(slots=True)
class Concept:
    id: str
    name: str
    description: str
    difficulty_level: int
    teach_content: str
    prerequisites: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ConceptKnowledge:
    concept_id: str
    p_mastery: float
    n_attempts: int
    n_correct: int
    n_wrong: int
    teach_shown: bool
    last_seen_at: str | None
    updated_at: str = ""


@dataclass(slots=True)
class MCQCard:
    id: int
    concept_id: str
    question: str
    correct_answer: str
    distractors: list[dict[str, str]]
    difficulty: int
    times_used: int
    content_hash: str
    source: str


def is_card_kind(value: str | None) -> bool:
    """Return True when value is a supported card kind."""

    if value is None:
        return False
    return value.strip().lower() in CARD_KINDS


def ensure_card_kind(value: str) -> CardKind:
    """Normalise and validate a card kind string."""

    normalized = value.strip().lower()
    if normalized not in CARD_KINDS:
        raise ValueError(f"Unsupported card kind: {value}")
    return cast(CardKind, normalized)


def normalize_direction(value: str | None) -> CardDirection | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized not in CARD_DIRECTIONS:
        raise ValueError(f"Unsupported card direction: {value}")
    return cast(CardDirection, normalized)


def card_kind_choices() -> Tuple[CardKind, ...]:
    return CARD_KINDS


def as_card_kind_sequence(values: Iterable[str]) -> tuple[CardKind, ...]:
    """Convert an iterable of strings into validated card kinds."""

    result: list[CardKind] = []
    for value in values:
        result.append(ensure_card_kind(value))
    return tuple(result)


__all__ = [
    "as_card_kind_sequence",
    "CARD_DIRECTIONS",
    "CARD_KINDS",
    "CardDirection",
    "CardKind",
    "CardRecord",
    "card_kind_choices",
    "Concept",
    "ConceptKnowledge",
    "ensure_card_kind",
    "is_card_kind",
    "LessonConcept",
    "LessonConceptExample",
    "LessonExercise",
    "LessonExerciseFeedback",
    "LessonDoc",
    "LessonDeckSummary",
    "LessonFillBlankEntry",
    "LessonVocabularyEntry",
    "CardDetail",
    "DeckSummary",
    "LessonInfo",
    "MCQCard",
    "normalize_direction",
    "FlowCardContext",
    "FlowResponse",
    "FlowSession",
    "PlayerProgress",
]
