"""Shared configuration: constants, persona registry, path helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Core config
# ---------------------------------------------------------------------------

LEARNER_ID = "artem"  # Phase 1: single user
MODEL = "claude-opus-4-7"
MAX_TOKENS = 2048
TRANSLATE_MODEL = "claude-haiku-4-5-20251001"

APP_DIR = Path(__file__).parent
FRAMEWORK_PATH = APP_DIR / "tutor_framework.md"
PERSONAS_DIR = APP_DIR / "personas"

# ---------------------------------------------------------------------------
# Persona registry
# ---------------------------------------------------------------------------

PERSONA_REGISTRY: dict[str, dict[str, Any]] = {
    "tutor": {
        "name": "Tutor",
        "region": "Your Spanish tutor",
        "bio": "Structured lessons, quizzes, vocab drills, and grammar. Manages your learning path.",
        "welcome_sub": "Lessons, quizzes & progress",
        "bubble_bg": "#EDE8F5",
        "bubble_border": "rgba(90, 60, 140, 0.16)",
        "bubble_name_color": "#5A3C8C",
        "avatar_template": "partials/avatar_tutor.html",
    },
    "marta": {
        "name": "Marta",
        "region": "Sevilla",
        "bio": "Spanish teacher. Warm, teasing, loves hiking and slow mornings.",
        "welcome_sub": "Tu profesora de español",
        "bubble_bg": "#F4ECE4",
        "bubble_border": "rgba(168, 110, 75, 0.14)",
        "bubble_name_color": "#8B5A3C",
        "avatar_template": "partials/avatar_marta.html",
    },
    "diego": {
        "name": "Diego",
        "region": "Madrid",
        "bio": "22, engineering student in Madrid. Football-obsessed.",
        "welcome_sub": "Tu amigo madrileño",
        "bubble_bg": "#EFEDE2",
        "bubble_border": "rgba(40, 90, 60, 0.18)",
        "bubble_name_color": "#2D5A3D",
        "avatar_template": "partials/avatar_diego.html",
    },
    "rosa": {
        "name": "Abuela Rosa",
        "region": "Granada",
        "bio": "Grandmother from Granada. Always asking if you've eaten.",
        "welcome_sub": "Tu abuela favorita",
        "bubble_bg": "#F3E9DC",
        "bubble_border": "rgba(160, 80, 40, 0.18)",
        "bubble_name_color": "#9A4E2C",
        "avatar_template": "partials/avatar_rosa.html",
    },
    "luis": {
        "name": "Luis",
        "region": "Madrid",
        "bio": "PM at a Madrid fintech. Drops English loanwords constantly.",
        "welcome_sub": "Tu colega de oficina",
        "bubble_bg": "#EBEDF0",
        "bubble_border": "rgba(40, 60, 100, 0.18)",
        "bubble_name_color": "#3D5A8C",
        "avatar_template": "partials/avatar_luis.html",
    },
}


def persona_path(persona_id: str) -> Path:
    return PERSONAS_DIR / f"{persona_id}.md"
