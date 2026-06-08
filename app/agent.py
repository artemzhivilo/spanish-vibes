"""Claude agent loop: runs one user-turn through the model.

Handles tool execution (fill-in-blank, MCQ, flashcards, grammar notes,
quiz sets, placement tests, and note saving), then loops until end_turn.
"""

from __future__ import annotations

import json
import random
import re
import secrets
from typing import Any

import anthropic

from .config import (
    FRAMEWORK_PATH,
    MAX_TOKENS,
    MODEL,
    persona_path,
)
from .database import (
    get_learner_notes,
    get_learner_summary,
    save_learner_notes,
    track_word,
    update_grammar_status,
    update_learner_profile,
)
from .placement_questions import QUESTION_BANK, PlacementQuestion, level_to_cefr
from .state import ACTIVE_PERSONA, QUIZZES, get_history
from .tools import TOOLS

client = anthropic.Anthropic()  # picks up ANTHROPIC_API_KEY

# ---------------------------------------------------------------------------
# Placement test helpers
# ---------------------------------------------------------------------------

PLACEMENT_TOTAL = 12


def pick_placement_question(
    difficulty: float, asked_indices: set[int]
) -> tuple[int, PlacementQuestion] | None:
    candidates = [(i, q) for i, q in enumerate(QUESTION_BANK) if i not in asked_indices]
    if not candidates:
        return None
    candidates.sort(key=lambda pair: (abs(pair[1].level - difficulty), random.random()))
    return candidates[0]


def compute_placement_result(quiz: dict[str, Any]) -> dict[str, Any]:
    results = quiz["results"]
    level_buckets: dict[str, dict[str, int]] = {}
    for r in results:
        label = r["level_label"]
        if label not in level_buckets:
            level_buckets[label] = {"correct": 0, "total": 0}
        level_buckets[label]["total"] += 1
        if r["correct"]:
            level_buckets[label]["correct"] += 1

    correct_levels = [r["level"] for r in results if r["correct"]]
    avg_correct = sum(correct_levels) / len(correct_levels) if correct_levels else 0.0
    estimated_level = level_to_cefr(avg_correct)

    level_order = ["A1", "A1-A2", "A2", "A2-B1", "B1", "B1-B2"]
    breakdown = []
    for label in level_order:
        if label in level_buckets:
            b = level_buckets[label]
            pct = round(b["correct"] / b["total"] * 100) if b["total"] > 0 else 0
            breakdown.append(
                {
                    "label": label,
                    "correct": b["correct"],
                    "total": b["total"],
                    "pct": pct,
                }
            )

    gaps = []
    for r in results:
        if not r["correct"] and r["grammar_topic"] not in gaps:
            gaps.append(r["grammar_topic"])

    parts = [f"{b['correct']}/{b['total']} {b['label']} correct" for b in breakdown]
    gap_str = ", ".join(gaps) if gaps else "none identified"
    summary_text = (
        f"[Placement test complete: estimated level {estimated_level}. "
        f"Breakdown: {'; '.join(parts)}. Grammar gaps: {gap_str}.]"
    )

    return {
        "level": estimated_level,
        "breakdown": breakdown,
        "gaps": gaps,
        "summary_text": summary_text,
    }


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------


def build_system_prompt(learner_id: str, persona_id: str | None = None) -> str:
    if persona_id is None:
        persona_id = ACTIVE_PERSONA.get(learner_id, "marta")
    # Get freeform notes from DB
    freeform_notes = get_learner_notes(learner_id)
    if not freeform_notes:
        freeform_notes = "_(no notes yet — first session)_"
    # Build combined learner context
    structured = get_learner_summary(learner_id)
    if structured:
        combined_notes = structured + "\n\n---\n\n## Freeform notes\n" + freeform_notes
    else:
        combined_notes = freeform_notes
    framework = FRAMEWORK_PATH.read_text().replace("{learner_notes}", combined_notes)
    p_path = persona_path(persona_id)
    persona = (
        p_path.read_text() if p_path.exists() else persona_path("marta").read_text()
    )
    return framework + "\n\n---\n\n" + persona


# ---------------------------------------------------------------------------
# Notes sync
# ---------------------------------------------------------------------------


def _sync_notes_to_db(learner_id: str, notes_md: str) -> None:
    """Parse structured info from notes and update the DB."""
    updates: dict[str, Any] = {"notes_md": notes_md}

    cefr_match = re.search(r"\b(A1|A2|B1|B2)\b", notes_md)
    if cefr_match:
        updates["cefr_level"] = cefr_match.group(1)

    about_match = re.search(
        r"##\s*About\s+them\s*\n(.*?)(?=\n##|\Z)",
        notes_md,
        re.DOTALL | re.IGNORECASE,
    )
    if about_match:
        about_text = about_match.group(1).strip()
        interests: list[str] = []
        interest_match = re.search(
            r"interests?[:\s]+(.+?)(?:\n|$)", about_text, re.IGNORECASE
        )
        if interest_match:
            raw = interest_match.group(1)
            interests = [i.strip().strip(".-*") for i in raw.split(",") if i.strip()]
        else:
            love_match = re.findall(
                r"(?:loves?|enjoys?|likes?|interested in|into)\s+(.+?)(?:\n|$)",
                about_text,
                re.IGNORECASE,
            )
            for raw in love_match:
                for part in re.split(r"\s+and\s+|,\s*", raw):
                    cleaned = part.strip().strip(".-*")
                    if cleaned and len(cleaned) < 50:
                        interests.append(cleaned)
        if interests:
            updates["interests"] = json.dumps(interests)

    update_learner_profile(learner_id, **updates)


def track_quiz_grammar(learner_id: str, topic: str, correct: int, total: int) -> None:
    if total == 0:
        return
    ratio = correct / total
    topic_key = re.sub(r"[^a-z0-9]+", "_", topic.lower()).strip("_")
    if ratio >= 0.85:
        status = "solid"
    elif ratio >= 0.5:
        status = "shaky"
    else:
        status = "gap"
    evidence = f"{correct}/{total} correct"
    update_grammar_status(learner_id, topic_key, status, evidence)


# ---------------------------------------------------------------------------
# Agent loop
# ---------------------------------------------------------------------------


def run_agent_turn(
    learner_id: str, user_text: str | None, persona_id: str | None = None
) -> dict[str, Any]:
    """Run one user-turn through Claude.

    Returns {"text": str, "cards": [...]}
    """
    if persona_id is None:
        persona_id = ACTIVE_PERSONA.get(learner_id, "marta")
    history = get_history(learner_id, persona_id)
    if user_text is not None:
        history.append({"role": "user", "content": user_text})

    rendered_cards: list[dict[str, Any]] = []
    system = build_system_prompt(learner_id, persona_id)

    while True:
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=[
                {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}
            ],
            tools=TOOLS,
            thinking={"type": "adaptive"},
            messages=history,
        )

        if response.stop_reason == "end_turn":
            history.append({"role": "assistant", "content": response.content})
            text = "".join(b.text for b in response.content if b.type == "text").strip()
            return {"text": text, "cards": rendered_cards}

        if response.stop_reason != "tool_use":
            history.append({"role": "assistant", "content": response.content})
            text = "".join(b.text for b in response.content if b.type == "text").strip()
            return {"text": text or "…", "cards": rendered_cards}

        # tool_use: execute every tool call, append results, loop
        history.append({"role": "assistant", "content": response.content})
        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            result = _execute_tool(block, learner_id, rendered_cards)
            tool_results.append(result)
        history.append({"role": "user", "content": tool_results})


def _execute_tool(
    block: Any, learner_id: str, rendered_cards: list[dict[str, Any]]
) -> dict[str, Any]:
    """Execute a single tool call and return the tool_result dict."""

    if block.name == "create_fill_in_blank":
        card_id = secrets.token_urlsafe(8)
        sentences = block.input["sentences"]
        QUIZZES[card_id] = {
            "sentences": sentences,
            "blanks_remaining": len(sentences),
            "results": [],
        }
        rendered_cards.append(
            {
                "type": "fill_blank",
                "id": card_id,
                "intro": block.input["intro"],
                "sentences": [
                    {
                        "idx": i,
                        "text_with_blank": s["text_with_blank"],
                        "hint": s.get("hint"),
                    }
                    for i, s in enumerate(sentences)
                ],
            }
        )
        return {
            "type": "tool_result",
            "tool_use_id": block.id,
            "content": f"Exercise rendered with {len(sentences)} blanks. The learner is working through them now.",
        }

    elif block.name == "create_multiple_choice":
        card_id = secrets.token_urlsafe(8)
        QUIZZES[card_id] = {
            "type": "mcq",
            "correct_index": block.input["correct_index"],
            "explanation": block.input["explanation"],
        }
        rendered_cards.append(
            {
                "type": "mcq",
                "id": card_id,
                "intro": block.input["intro"],
                "question": block.input["question"],
                "options": block.input["options"],
            }
        )
        return {
            "type": "tool_result",
            "tool_use_id": block.id,
            "content": "Multiple-choice question rendered. Waiting for answer.",
        }

    elif block.name == "create_flashcard_set":
        rendered_cards.append(
            {
                "type": "flashcard_set",
                "id": secrets.token_urlsafe(8),
                "intro": block.input["intro"],
                "cards": block.input["cards"],
            }
        )
        for fc in block.input["cards"]:
            track_word(
                learner_id, word=fc["front"], translation=fc["back"], domain=None
            )
        return {
            "type": "tool_result",
            "tool_use_id": block.id,
            "content": f"Flashcard set with {len(block.input['cards'])} cards rendered.",
        }

    elif block.name == "create_grammar_note":
        rendered_cards.append(
            {
                "type": "grammar_note",
                "id": secrets.token_urlsafe(8),
                "title": block.input["title"],
                "explanation": block.input["explanation"],
                "examples": block.input["examples"],
            }
        )
        return {
            "type": "tool_result",
            "tool_use_id": block.id,
            "content": "Grammar note rendered.",
        }

    elif block.name == "create_quiz_set":
        card_id = secrets.token_urlsafe(8)
        questions = block.input["questions"]
        QUIZZES[card_id] = {
            "type": "quiz_set",
            "topic": block.input.get("topic", ""),
            "questions": list(questions),
            "current_index": 0,
            "original_count": len(questions),
            "results": [],
        }
        rendered_cards.append(
            {
                "type": "quiz_set",
                "id": card_id,
                "intro": block.input["intro"],
                "topic": block.input["topic"],
                "question": questions[0],
                "current": 1,
                "total": len(questions),
            }
        )
        return {
            "type": "tool_result",
            "tool_use_id": block.id,
            "content": f"Quiz set with {len(questions)} questions rendered.",
        }

    elif block.name == "run_placement_test":
        card_id = secrets.token_urlsafe(8)
        difficulty = 2.0
        first_pick = pick_placement_question(difficulty, set())
        if first_pick is None:
            return {
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": "Error: no questions available.",
                "is_error": True,
            }
        q_idx, q = first_pick
        QUIZZES[card_id] = {
            "type": "placement",
            "difficulty": difficulty,
            "asked_indices": [q_idx],
            "current_question": q,
            "current_index": 0,
            "total": PLACEMENT_TOTAL,
            "results": [],
        }
        rendered_cards.append(
            {
                "type": "placement",
                "id": card_id,
                "intro": "Let's see where you are! 12 quick questions — just pick the best answer.",
                "question": {"question": q.question, "options": q.options},
                "current": 1,
                "total": PLACEMENT_TOTAL,
            }
        )
        return {
            "type": "tool_result",
            "tool_use_id": block.id,
            "content": f"Placement test started ({PLACEMENT_TOTAL} questions).",
        }

    elif block.name == "save_learner_notes":
        notes_text = block.input["notes"]
        save_learner_notes(learner_id, notes_text)
        _sync_notes_to_db(learner_id, notes_text)
        return {
            "type": "tool_result",
            "tool_use_id": block.id,
            "content": "Notes saved and learner profile updated.",
        }

    else:
        return {
            "type": "tool_result",
            "tool_use_id": block.id,
            "content": f"Unknown tool: {block.name}",
            "is_error": True,
        }
