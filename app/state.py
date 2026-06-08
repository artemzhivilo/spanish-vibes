"""In-memory session state (single user, single process — Phase 1).

These data structures live in memory for the current server process.
Chat log is also persisted to the database for survival across restarts.
"""

from __future__ import annotations

from typing import Any

from .config import LEARNER_ID

# ---------------------------------------------------------------------------
# Active persona per learner
# ---------------------------------------------------------------------------

ACTIVE_PERSONA: dict[str, str] = {LEARNER_ID: "tutor"}

# ---------------------------------------------------------------------------
# Conversation history per (learner, persona) pair
# (Anthropic message-list format — used for the Claude API call)
# ---------------------------------------------------------------------------

HISTORY: dict[tuple[str, str], list[dict[str, Any]]] = {}


def get_history(learner_id: str, persona_id: str) -> list[dict[str, Any]]:
    """Return the API conversation history for a learner-persona pair."""
    key = (learner_id, persona_id)
    if key not in HISTORY:
        HISTORY[key] = []
    return HISTORY[key]


# ---------------------------------------------------------------------------
# Pending quizzes / exercises
# ---------------------------------------------------------------------------

QUIZZES: dict[str, dict[str, Any]] = {}
