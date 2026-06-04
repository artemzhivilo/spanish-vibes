"""Agent-based tutor orchestrator for Spanish Vibes.

Single-provider design: all models (planner and workers) use the OpenAI SDK.
The planner model (gpt-5.2) is configured in data/prompts.yaml tutor.planner.
Worker models for conversation/evaluation stay in the prompts.yaml models section.

Architecture:
  TutorSession            — holds state, reads markdown memory files at init
      │
      └─ plan_next_action()   — builds context → calls planner → TutorAction
              │
              └─ TutorAction  — tool_name + params + worker_briefing + tutor_message

The caller (tutor_routes.py) takes the TutorAction, passes it to
tutor_tools.py for execution, then sends the HTML partial to HTMX.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from .flow_ai import _get_client, ai_available
from .tutor_memory import (
    build_planner_context,
    append_session_journal,
    update_grammar_concept,
    write_learner_profile,
    # backward-compat names still resolved above if anything calls them
)


# ── Paths ─────────────────────────────────────────────────────────────────────

_PACKAGE_ROOT = Path(__file__).resolve().parent
_PROJECT_ROOT = _PACKAGE_ROOT.parent.parent
_PROMPTS_PATH = _PROJECT_ROOT / "data" / "prompts.yaml"


# ── Planner config ────────────────────────────────────────────────────────────


def _get_planner_cfg() -> dict[str, Any]:
    """Read tutor.planner section from data/prompts.yaml."""
    try:
        data: dict[str, Any] = (
            yaml.safe_load(_PROMPTS_PATH.read_text(encoding="utf-8")) or {}
        )
    except Exception:
        data = {}
    return data.get("tutor", {}).get("planner", {})


# ── Planner system prompt ─────────────────────────────────────────────────────

_PLANNER_SYSTEM = """\
You are an expert Spanish language tutor supporting learners at any level and for any goal.

{memory_context}

---

YOUR ROLE:
Decide what learning activity to give the learner next. You have tools that
create interactive exercises. Pick the right tool based on:

1. WHAT THEY NEED: Look at grammar_notes for the biggest current weakness.
   Target that concept — don't spread attention across multiple things at once.

2. ACTIVITY VARIETY: Don't repeat the same activity type back-to-back.
   Ideal arc: conversation → drill → conversation, or drill → feedback → conversation.

3. ENERGY LEVEL: If the session has run 20+ minutes, start wrapping up.
   If the learner is making progress, maintain momentum.

4. TASK TYPE VARIETY: Over multiple sessions, ensure exposure to different
   activity types: conversation, conjugation drill, translation, describe an
   image in Spanish, and free-expression writing. Not all in one session.

5. INTERESTS: Use interests from the learner profile to theme activities.
   Grammar in context beats grammar in the abstract.

PEDAGOGICAL PRINCIPLES:
- Production over recognition: make them write and speak, not just click.
- The struggle zone: target ~70-80% success rate — hard enough to require
  thinking, not so hard they shut down.
- Transfer: after a drill, test the same form in a conversation.
  That is where learning consolidates.
- Don't ask "what do you want to do?" — you lead.

CURRICULUM AWARENESS:
- The CURRICULUM STATUS section shows mastery data from the concept graph.
- Use it to pick the RIGHT concept to target - don't guess, check the data.
- If a concept shows many attempts but low mastery, it needs focused work
  (drill -> teach -> retry, not just more conversation).
- If a concept shows high mastery in drills but the grammar_notes say it
  fails in free speech, prioritize transfer practice (conversation).
- When choosing what to work on, prefer concepts that are:
  1. Currently in progress (some attempts, not yet mastered)
  2. Available (prerequisites met) but not started
  3. Stuck (many attempts, low mastery) - these need a different approach
- Don't introduce concepts whose prerequisites aren't met.
- The curriculum data gives you NUMBERS. The grammar_notes give you CONTEXT.
  Use both: the numbers tell you WHAT to work on, the notes tell you HOW.

SESSION RHYTHM:
- First call: propose_session_plan (welcome the learner, outline what you'll work on)
- Then: 2-4 activities mixing conversation, drills, and translation challenges
- Use the CURRICULUM STATUS to pick the right concept — target what's next available
  or what's stuck, not random topics
- Before ending: give_feedback with specific progress notes
- At session end: end_session → update_session_journal → update_grammar_notes

END SESSION OUTPUT FORMAT:
When calling end_session, provide concrete, card-ready fields:
- summary_message: warm closing message, 2-3 sentences.
- activities_summary: array of {{type, score, highlight}}.
- breakthroughs: short bullets for first-time wins or clear improvements.
- still_working_on: short bullets for what needs focus next.
- next_session_preview: one sentence about the next session plan.
- session_number: integer session count.

Only summary_message is required. If uncertain, include fewer optional fields
instead of hallucinating details.

CALL ONE TOOL. State your reasoning briefly (1-2 sentences), then call the tool.
The worker_briefing field is critical — fill it with specific, concrete context
about this learner right now so the cheap worker model can punch above its weight.
"""


# ── Tool schemas (OpenAI function-calling format) ─────────────────────────────

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "propose_session_plan",
            "description": (
                "Open the session by proposing a focus area and plan. "
                "MUST be the first tool called for returning learners. "
                "The learner can agree or redirect. "
                "For brand new learners, do not use this as a blocking check-in; "
                "start with guided activities immediately."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "tutor_message": {
                        "type": "string",
                        "description": (
                            "Opening message to the learner. "
                            "If this is a NEW learner (not yet assessed / no session history), "
                            "write a brief warm welcome only; do NOT ask them to choose or "
                            "describe experience before starting activities. "
                            "If there IS history, reference last session with specific details "
                            "(not 'last time' but 'last session you were mixing up tuve/teno'). "
                            "2-4 sentences, friendly and specific."
                        ),
                    },
                    "focus_concepts": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Concept IDs to target today (e.g. ['preterite_irregular', 'poder'])",
                    },
                    "suggested_activities": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Ordered activity types planned (e.g. ['conversation', 'conjugation_drill'])",
                    },
                    "session_goal": {
                        "type": "string",
                        "description": "One sentence: what success looks like this session",
                    },
                    "estimated_duration_min": {
                        "type": "integer",
                        "description": "Estimated duration in minutes (typically 15-25)",
                    },
                },
                "required": [
                    "tutor_message",
                    "focus_concepts",
                    "suggested_activities",
                    "session_goal",
                ],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "start_conversation",
            "description": (
                "Open a conversation with a Spanish-speaking persona. "
                "The learner chats in Spanish for several turns. "
                "Best for transfer practice — using grammar in free speech after drilling."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "tutor_message": {
                        "type": "string",
                        "description": (
                            "Brief English intro before the conversation. "
                            "Set expectations without revealing the exact topic. 1-2 sentences."
                        ),
                    },
                    "persona": {
                        "type": "string",
                        "description": "Persona slug (e.g. 'marta', 'diego'). Default: 'marta'",
                    },
                    "topic": {
                        "type": "string",
                        "description": "Conversation topic (e.g. 'what you did last weekend')",
                    },
                    "concept": {
                        "type": "string",
                        "description": (
                            "Grammar concept to target (e.g. 'preterite', 'gustar'). "
                            "For new/unknown learners use present-tense intro basics first."
                        ),
                    },
                    "difficulty": {
                        "type": "integer",
                        "description": (
                            "Scaffolding level 1-3 (1=maximum support, 3=minimum support). "
                            "For new/unknown learners, use 1."
                        ),
                    },
                    "max_turns": {
                        "type": "integer",
                        "description": "Maximum user turns (default 4)",
                    },
                    "guardrails": {
                        "type": "string",
                        "description": "Specific forms to target or avoid",
                    },
                    "worker_briefing": {
                        "type": "string",
                        "description": (
                            "Rich context injected into the conversation worker's system prompt. "
                            "Include: specific errors and their pattern (e.g. 'defaults to teno for tener preterite'), "
                            "why this conversation was chosen (transfer test, first attempt, etc.), "
                            "how to react if target form is used correctly, "
                            "learner's interests and humor style, what NOT to over-drill."
                        ),
                    },
                },
                "required": [
                    "tutor_message",
                    "topic",
                    "concept",
                    "difficulty",
                    "worker_briefing",
                ],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "show_conjugation_drill",
            "description": (
                "Rapid-fire verb conjugation drill. Learner types the conjugated form. "
                "Evaluated locally — no LLM needed. "
                "Use to build automaticity before attempting a form in free speech."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "tutor_message": {
                        "type": "string",
                        "description": "Brief intro before the drill (1-2 sentences)",
                    },
                    "verbs": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Infinitives to drill (e.g. ['tener', 'ir', 'hacer'])",
                    },
                    "tense": {
                        "type": "string",
                        "description": "Target tense (e.g. 'preterite', 'present', 'imperfect')",
                    },
                    "persons": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Persons to include (e.g. ['yo', 'tú', 'él/ella']). Omit for all.",
                    },
                    "count": {
                        "type": "integer",
                        "description": "Number of items (default 6, max 12)",
                    },
                    "worker_briefing": {
                        "type": "string",
                        "description": "Which specific forms the learner keeps getting wrong and why",
                    },
                },
                "required": ["tutor_message", "verbs", "tense", "worker_briefing"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "show_translation_challenge",
            "description": (
                "Shows English sentences one at a time. Learner writes each in Spanish. "
                "A worker model evaluates grammar, vocabulary, and communication success. "
                "Communication success is MOST IMPORTANT — did they convey the meaning? "
                "Grammar accuracy is secondary. Use to test if grammar can be used in "
                "production (writing), not just recognised."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "tutor_message": {
                        "type": "string",
                        "description": "Brief intro before the challenge (1-2 sentences)",
                    },
                    "sentences": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "English sentences to translate (2-5 recommended)",
                    },
                    "target_grammar": {
                        "type": "string",
                        "description": "Primary grammar focus (e.g. 'preterite_irregular', 'ser_vs_estar')",
                    },
                    "difficulty": {
                        "type": "integer",
                        "description": "Difficulty 1-3 (1=beginner, 2=intermediate, 3=upper-intermediate). Affects evaluator strictness.",
                    },
                    "hints": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional vocabulary hints shown on demand (e.g. ['tener = to have', 'ayer = yesterday'])",
                    },
                    "worker_briefing": {
                        "type": "string",
                        "description": (
                            "Context for the worker evaluator. Include: specific grammar forms to "
                            "watch for, what the learner has been struggling with, how lenient to be. "
                            "Communication success > grammar perfection."
                        ),
                    },
                },
                "required": [
                    "tutor_message",
                    "sentences",
                    "target_grammar",
                    "worker_briefing",
                ],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "show_circumlocution_challenge",
            "description": (
                "Give the learner a complex English idea to express in Spanish using "
                "whatever vocabulary they have. Tests communication strategy — the core "
                "skill of getting your point across when you lack the exact word. "
                "Evaluation prioritises communication success and creative workarounds "
                "over grammar accuracy. Use after translation or conversation practice "
                "to test free production without scaffolding."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "tutor_message": {
                        "type": "string",
                        "description": "Brief intro (1-2 sentences). Set expectations: no perfect translation needed, just get the idea across.",
                    },
                    "prompt_en": {
                        "type": "string",
                        "description": "The complex English idea to express. Can be multi-sentence. Use realistic life situations.",
                    },
                    "target_grammar": {
                        "type": "string",
                        "description": "Grammar the evaluator should watch for (e.g. 'preterite_irregular')",
                    },
                    "vocabulary_level": {
                        "type": "string",
                        "description": "Expected vocabulary ceiling: 'beginner', 'intermediate', or 'upper_intermediate'",
                    },
                    "hints": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional key vocabulary (shown on demand). Keep to 3-5 most blocking words.",
                    },
                    "worker_briefing": {
                        "type": "string",
                        "description": (
                            "Context for the worker evaluator. Include: what grammar to watch for, "
                            "specific workarounds that would count as success, "
                            "how lenient to be on grammar vs communication. "
                            "Be specific about what 'getting it across' looks like for this prompt."
                        ),
                    },
                },
                "required": [
                    "tutor_message",
                    "prompt_en",
                    "target_grammar",
                    "worker_briefing",
                ],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "give_feedback",
            "description": (
                "Show a feedback message between activities. "
                "Reference specific improvements or patterns. "
                "Keep to 1-3 sentences. Don't overuse — max once every 2 activities."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": (
                            "Specific feedback referencing exact forms or moments "
                            "(e.g. 'tuve was right 3 times today vs 0 last session!'). "
                            "Optionally preview what's next."
                        ),
                    },
                    "show_stats": {
                        "type": "boolean",
                        "description": "Whether to show a stats block alongside the message",
                    },
                    "stats": {
                        "type": "object",
                        "description": "Optional stats",
                        "properties": {
                            "correct_rate": {"type": "number"},
                            "focus_concept": {"type": "string"},
                            "highlight": {"type": "string"},
                        },
                    },
                },
                "required": ["message"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "end_session",
            "description": (
                "Wrap up the session. Call when activities are complete or the learner "
                "wants to stop. Follow with update_session_journal and update_grammar_notes."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "summary_message": {
                        "type": "string",
                        "description": (
                            "Closing message — achievements with numbers "
                            "(e.g. 'tuve: 3/4 today vs 0/3 last time'), "
                            "what still needs work, and what's next. Warm and specific."
                        ),
                    },
                    "activities_summary": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "type": {"type": "string"},
                                "score": {"type": "number"},
                                "highlight": {"type": "string"},
                            },
                            "required": ["type", "score", "highlight"],
                        },
                        "description": (
                            "Per-activity summary cards. Example type values: "
                            "'conversation', 'translation_challenge', 'conjugation_drill'."
                        ),
                    },
                    "breakthroughs": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "First-time wins or clear improvements this session",
                    },
                    "still_working_on": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Areas to continue practising next session",
                    },
                    "next_session_preview": {
                        "type": "string",
                        "description": "One sentence preview of next session's plan",
                    },
                    "session_number": {
                        "type": "integer",
                        "description": "1-based learner session count",
                    },
                },
                "required": ["summary_message"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_session_journal",
            "description": (
                "Append a new entry to the learner's session journal. "
                "Call AFTER end_session. Write what you'd want to know at the START of next session."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "entry": {
                        "type": "string",
                        "description": (
                            "Markdown journal entry. Include: date/session number, focus, "
                            "activities in order, key observations (specific errors with context, "
                            "breakthroughs, avoidance patterns, energy level), next session plan."
                        ),
                    },
                },
                "required": ["entry"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_grammar_notes",
            "description": (
                "Update grammar tracking for a specific concept. "
                "Call when you observe a meaningful change: breakthrough, new error pattern, "
                "status change, or confirmed avoidance."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "concept": {
                        "type": "string",
                        "description": "Grammar concept (e.g. 'preterite_irregular_tener')",
                    },
                    "status": {
                        "type": "string",
                        "enum": [
                            "WEAK",
                            "IN_PROGRESS",
                            "SOLID",
                            "AVOIDANCE",
                            "NOT_YET_INTRODUCED",
                        ],
                    },
                    "update": {
                        "type": "string",
                        "description": (
                            "Specific evidence with numbers. "
                            "E.g. 'Used tuve correctly 3/4 times in conversation. "
                            "Still reverts to teno under time pressure.'"
                        ),
                    },
                },
                "required": ["concept", "update"],
            },
        },
    },
]

# Names of tools that update memory files and produce no HTML
_MEMORY_TOOLS = frozenset({"update_session_journal", "update_grammar_notes"})


# ── Dataclasses ───────────────────────────────────────────────────────────────


@dataclass
class TutorActivityResult:
    """Result from a completed activity, passed back to the planner."""

    activity_type: str  # "conversation", "conjugation_drill", …
    score: float  # 0.0 – 1.0
    errors: list[str]  # specific errors e.g. ["tener→tuve: said 'teno'"]
    concepts_practiced: list[str]
    notes: str  # human-readable summary the planner reads
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class TutorAction:
    """What the planner decided to do next."""

    tool_name: str
    params: dict[str, Any]
    worker_briefing: str  # extracted from params for convenience
    tutor_message: str  # what the tutor says before/with the activity

    @property
    def is_memory_tool(self) -> bool:
        return self.tool_name in _MEMORY_TOOLS


@dataclass
class ChatMessage:
    """A message in the tutor ↔ learner chat."""

    role: str  # "tutor" | "learner"
    content: str
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


# ── TutorSession ──────────────────────────────────────────────────────────────


@dataclass
class DebugPromptEntry:
    """One captured LLM call for the dev tools panel."""

    timestamp: str
    label: str  # "planner", "opener", "respond", "translation_eval", …
    model: str
    system_prompt: str
    user_message: str
    tool_result: str  # JSON of what came back (tool call or raw text)


class TutorSession:
    """
    Holds all state for one tutor session and drives the planner loop.

    Typical lifecycle:
        session = TutorSession(session_id, user_id)
        action  = session.plan_next_action()            # → propose_session_plan
        ...
        action  = session.plan_next_action(last_result) # after each activity
        if action.is_memory_tool:
            session.execute_memory_tool(action)         # journal / notes
    """

    def __init__(self, session_id: str, user_id: str) -> None:
        self.session_id = session_id
        self.user_id = user_id
        self.activities: list[TutorActivityResult] = []
        self.current_activity: str | None = None
        self.message_history: list[ChatMessage] = []
        self.started_at = datetime.now(timezone.utc).isoformat()

        # Dev tools: captured prompts for inspection
        self.debug_log: list[DebugPromptEntry] = []

        # Session number from DB (how many sessions this user has had)
        try:
            from .tutor_db import count_user_sessions

            self.session_number: int = count_user_sessions(user_id) + 1
        except Exception:
            self.session_number = 1

        # Load memory files once at session start; _memory_context is
        # refreshed from disk after any write via _reload_memory().
        self._memory_context = build_planner_context(user_id)

    # ── Memory ────────────────────────────────────────────────────────────────

    def _reload_memory(self) -> None:
        """Re-read all memory files from disk after any write."""
        self._memory_context = build_planner_context(self.user_id)

    def update_journal(self, entry: str) -> None:
        append_session_journal(self.user_id, entry)
        self._reload_memory()

    def update_grammar_notes(
        self, concept: str, status: str | None, update: str
    ) -> None:
        update_grammar_concept(self.user_id, concept, status, update)
        self._reload_memory()

    def rewrite_profile(self, new_content: str) -> None:
        write_learner_profile(self.user_id, new_content)
        self._reload_memory()

    # ── State ─────────────────────────────────────────────────────────────────

    def record_activity(self, result: TutorActivityResult) -> None:
        self.activities.append(result)
        self.current_activity = None

    def add_message(self, role: str, content: str) -> None:
        self.message_history.append(ChatMessage(role=role, content=content))

    # ── Planner calls ─────────────────────────────────────────────────────────

    def _build_system_prompt(self) -> str:
        return _PLANNER_SYSTEM.format(memory_context=self._memory_context)

    def _is_new_learner(self) -> bool:
        """True only for the very first session (no prior DB records).

        Uses the DB session count (reliable, code-driven) rather than
        regex on the markdown journal (fragile — depends on the LLM
        writing a journal entry AND the background thread succeeding).
        """
        return self.session_number <= 1

    def _build_user_message(self, last_result: TutorActivityResult | None) -> str:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        session_num = self.session_number

        # Check whether the session plan has already been proposed.
        # If the learner has replied (message_history has a learner turn)
        # but no activity has started yet, the plan was accepted — start the first activity.
        plan_already_proposed = any(m.role == "learner" for m in self.message_history)

        if not self.activities and last_result is None and not plan_already_proposed:
            if self._is_new_learner():
                return (
                    f"Start session #{session_num}. "
                    f"Date: {date_str}. "
                    "This is a NEW learner (not yet assessed / no prior session history). "
                    "Skip back-and-forth planning and start immediately with the first "
                    "guided activity in the new-learner arc (hinted translation basics)."
                )
            return (
                f"Start session #{session_num}. "
                f"Date: {date_str}. "
                f"This is a RETURNING learner (session #{session_num}). "
                "Do NOT use the new-learner arc. "
                "Call propose_session_plan to open the session, referencing "
                "their history and planning activities based on their current level."
            )

        if not self.activities and last_result is None and plan_already_proposed:
            learner_replies = [
                m.content for m in self.message_history if m.role == "learner"
            ]
            last_reply = learner_replies[-1] if learner_replies else "Sounds good."
            return (
                f"Session #{session_num} ({date_str}). "
                f"Session plan was already proposed. "
                f'Learner replied: "{last_reply}". '
                "Start the first planned activity now. Do NOT call propose_session_plan again."
            )

        lines = [f"Session #{session_num} ({date_str}). Activities so far:"]
        for i, act in enumerate(self.activities, 1):
            line = f"  {i}. {act.activity_type}: {act.score:.0%} score" + (
                f", errors: {'; '.join(act.errors[:3])}" if act.errors else ""
            )
            lines.append(line)
            if act.notes:
                lines.append(f"     {act.notes}")

        if last_result is not None:
            lines += [
                "\nMost recent activity just finished:",
                f"  Type:  {last_result.activity_type}",
                f"  Score: {last_result.score:.0%}",
            ]
            if last_result.errors:
                lines.append(f"  Errors: {'; '.join(last_result.errors[:5])}")
            if last_result.notes:
                lines.append(f"  Notes: {last_result.notes}")

        # Include recent learner messages so planner can respond to quit requests, etc.
        recent_learner = [m for m in self.message_history if m.role == "learner"][-3:]
        if recent_learner:
            lines.append("\nRecent learner messages (most recent last):")
            for m in recent_learner:
                lines.append(f"  Learner: {m.content!r}")
            # Explicit end-session check
            last_msg = recent_learner[-1].content.lower()
            quit_signals = [
                "enough",
                "stop",
                "finish",
                "done",
                "bye",
                "end",
                "quit",
                "exit",
                "gracias",
                "merci",
            ]
            if any(q in last_msg for q in quit_signals):
                lines.append(
                    "\nLEARNER WANTS TO END THE SESSION. Call end_session now."
                )

        lines.append("\nWhat should we do next? Call the appropriate tool.")
        return "\n".join(lines)

    def plan_next_action(
        self,
        last_result: TutorActivityResult | None = None,
        context_override: str | None = None,
    ) -> TutorAction:
        """Call the planner and return the next TutorAction."""
        if not ai_available():
            return _fallback_action()

        system = self._build_system_prompt()
        user_msg = context_override or self._build_user_message(last_result)
        cfg = _get_planner_cfg()

        raw = _call_planner(system, user_msg, cfg)
        action = _parse_response(raw)

        # Capture for dev tools
        self.debug_log.append(
            DebugPromptEntry(
                timestamp=datetime.now(timezone.utc).isoformat(),
                label="planner",
                model=cfg.get("model", "gpt-4o"),
                system_prompt=system,
                user_message=user_msg,
                tool_result=json.dumps(raw, indent=2, ensure_ascii=False),
            )
        )
        return action

    def log_worker_call(
        self,
        label: str,
        model: str,
        system_prompt: str,
        user_message: str,
        result: str = "",
    ) -> None:
        """Log a worker LLM call for dev tools inspection."""
        self.debug_log.append(
            DebugPromptEntry(
                timestamp=datetime.now(timezone.utc).isoformat(),
                label=label,
                model=model,
                system_prompt=system_prompt,
                user_message=user_message,
                tool_result=result,
            )
        )

    def execute_memory_tool(self, action: TutorAction) -> None:
        """Run a memory-update tool (no HTML output)."""
        if action.tool_name == "update_session_journal":
            self.update_journal(action.params.get("entry", ""))
        elif action.tool_name == "update_grammar_notes":
            self.update_grammar_notes(
                concept=action.params.get("concept", "unknown"),
                status=action.params.get("status"),
                update=action.params.get("update", ""),
            )


# ── Planner caller ────────────────────────────────────────────────────────────


def _call_planner(
    system: str,
    user_msg: str,
    cfg: dict[str, Any],
) -> dict[str, Any]:
    """
    Call the OpenAI planner with tool_choice='required'.
    Returns {name: str, params: dict}.
    """
    client = _get_client()
    if client is None:
        return _fallback_raw()

    model = cfg.get("model", "gpt-4o")
    temperature = float(cfg.get("temperature", 0.3))
    max_completion_tokens = int(cfg.get("max_tokens", 1500))

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_msg},
            ],
            tools=TOOL_SCHEMAS,
            tool_choice="required",
            temperature=temperature,
            max_completion_tokens=max_completion_tokens,
        )
        msg = response.choices[0].message
        if not msg.tool_calls:
            return _fallback_raw()
        call = msg.tool_calls[0]
        return {
            "name": call.function.name,
            "params": json.loads(call.function.arguments),
        }
    except Exception as e:
        import logging

        logging.getLogger(__name__).error(
            "Planner call failed (model=%s): %s", model, e
        )
        return _fallback_raw()


def _parse_response(raw: dict[str, Any]) -> TutorAction:
    name = raw.get("name", "give_feedback")
    params = raw.get("params", {})
    tutor_message = (
        params.get("tutor_message")
        or params.get("message")
        or params.get("summary_message")
        or ""
    )
    return TutorAction(
        tool_name=name,
        params=params,
        worker_briefing=params.get("worker_briefing", ""),
        tutor_message=str(tutor_message),
    )


def _fallback_raw() -> dict[str, Any]:
    return {
        "name": "give_feedback",
        "params": {
            "message": (
                "Having a bit of trouble connecting right now. "
                "Let's jump straight in — ¡vamos!"
            ),
            "show_stats": False,
        },
    }


def _fallback_action() -> TutorAction:
    return _parse_response(_fallback_raw())


# ── Public API ────────────────────────────────────────────────────────────────

__all__ = [
    "DebugPromptEntry",
    "TOOL_SCHEMAS",
    "ChatMessage",
    "TutorAction",
    "TutorActivityResult",
    "TutorSession",
]
