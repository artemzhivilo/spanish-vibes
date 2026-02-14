"""Conversation type selection and prompt instructions for flow conversations."""

from __future__ import annotations

import random
from typing import Literal

from .concepts import load_concepts
from .flow_db import get_all_concept_knowledge

ConversationType = Literal[
    "general_chat",
    "role_play",
    "concept_required",
    "tutor",
    "story_comprehension",
]

BASE_TYPE_WEIGHTS: dict[ConversationType, float] = {
    "general_chat": 0.45,
    "role_play": 0.20,
    "concept_required": 0.15,
    "tutor": 0.10,
    "story_comprehension": 0.10,
}

CONVERSATION_TYPE_INSTRUCTIONS: dict[ConversationType, str | None] = {
    "general_chat": (
        "CONVERSATION MODE: General Chat\n"
        "Have a natural, free-form conversation. Talk about whatever interests you both. "
        "Share your own stories and opinions. Ask follow-up questions. "
        "There's no specific learning goal; just enjoy chatting in Spanish."
    ),
    "role_play": (
        "CONVERSATION MODE: Role Play\n"
        "You are playing a specific role in a scenario. Stay in character for the scenario. "
        "Guide the learner through the situation naturally and do not break character.\n\n"
        "SCENARIO: {scenario}"
    ),
    "concept_required": (
        "CONVERSATION MODE: Concept Practice\n"
        "Have a natural conversation, but steer it so the learner needs to use {concept_name}. "
        "Do not explicitly tell them what to practice. Ask questions that naturally require {concept_name}. "
        "If they avoid it, redirect with a more specific follow-up."
    ),
    "tutor": (
        "CONVERSATION MODE: Tutor\n"
        "Today you are helping the learner with {concept_name}. "
        "Teach through examples and natural conversation, not lectures. "
        "Give a brief example, ask them to try, then gently correct while staying warm and encouraging."
    ),
    "story_comprehension": None,
}

ROLE_PLAY_SCENARIOS: dict[str, list[str]] = {
    "food_cooking": [
        "You are a waiter at a tapas restaurant in Madrid. The learner is ordering dinner. Suggest dishes and ask about preferences.",
        "You are a vendor at a neighborhood market. The learner wants ingredients for a recipe. Negotiate prices and suggest alternatives.",
    ],
    "travel": [
        "You are a stranger on the street. The learner is lost and asks for directions to the train station.",
        "You are a hotel receptionist. The learner is checking in. Ask for reservation details and explain breakfast hours.",
    ],
    "sports": [
        "You are a ticket seller at a football stadium. The learner wants tickets for tonight's match.",
        "You are a fitness trainer at a gym. The learner is signing up and discussing their fitness goals.",
    ],
}

_TOPIC_TO_SCENARIO_KEY: dict[str, str] = {
    "food": "food_cooking",
    "comida": "food_cooking",
    "cooking": "food_cooking",
    "travel": "travel",
    "viajes": "travel",
    "sports": "sports",
    "deportes": "sports",
    "football": "sports",
}


def select_conversation_type(
    concept_id: str,
    session_id: int,
) -> tuple[ConversationType, str | None]:
    """Select conversation type and optional target concept."""
    _ = session_id

    stuck_concept = _find_stuck_concept(preferred_concept_id=concept_id)
    if stuck_concept:
        return "concept_required", stuck_concept

    choices = list(BASE_TYPE_WEIGHTS.keys())
    weights = [BASE_TYPE_WEIGHTS[choice] for choice in choices]
    selected = random.choices(choices, weights=weights, k=1)[0]

    if selected in {"concept_required", "tutor"}:
        return selected, concept_id
    return selected, None


def get_type_instruction(
    conversation_type: ConversationType,
    *,
    concept_id: str,
    topic: str,
    persona_id: str | None = None,
) -> str | None:
    template = CONVERSATION_TYPE_INSTRUCTIONS.get(conversation_type)
    if not template:
        return None

    concepts = load_concepts()
    concept_name = concepts.get(concept_id).name if concept_id in concepts else concept_id

    if conversation_type == "role_play":
        scenario = select_role_play_scenario(topic=topic, persona_id=persona_id)
        if not scenario:
            return CONVERSATION_TYPE_INSTRUCTIONS["general_chat"]
        return template.format(scenario=scenario)

    if conversation_type in {"concept_required", "tutor"}:
        return template.format(concept_name=concept_name)

    return template


def select_role_play_scenario(topic: str, persona_id: str | None = None) -> str | None:
    _ = persona_id
    key = _infer_scenario_key(topic)
    if not key:
        return None
    scenarios = ROLE_PLAY_SCENARIOS.get(key) or []
    if not scenarios:
        return None
    return random.choice(scenarios)


def _infer_scenario_key(topic: str) -> str | None:
    normalized = topic.strip().lower().replace("&", " ").replace("-", " ")
    for token, mapped in _TOPIC_TO_SCENARIO_KEY.items():
        if token in normalized:
            return mapped
    return None


def _find_stuck_concept(preferred_concept_id: str) -> str | None:
    knowledge = get_all_concept_knowledge()
    preferred = knowledge.get(preferred_concept_id)
    if preferred and preferred.n_attempts >= 5 and preferred.p_mastery < 0.7:
        return preferred_concept_id

    candidates = [
        ck
        for ck in knowledge.values()
        if ck.n_attempts >= 5 and ck.p_mastery < 0.7
    ]
    if not candidates:
        return None

    candidates.sort(key=lambda ck: (ck.p_mastery, -ck.n_attempts))
    return candidates[0].concept_id


__all__ = [
    "BASE_TYPE_WEIGHTS",
    "CONVERSATION_TYPE_INSTRUCTIONS",
    "ROLE_PLAY_SCENARIOS",
    "ConversationType",
    "get_type_instruction",
    "select_conversation_type",
    "select_role_play_scenario",
]

