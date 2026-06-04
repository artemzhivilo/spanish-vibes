"""Spanish Vibes — Phase 1 walking skeleton.

A FastAPI + HTMX app where a single Claude agent chats in Spanish as Marta,
drops one inline fill_in_blank exercise when it makes sense, reacts to the
learner's answers, and saves learner notes to disk at the end of the session.

Memory layer is parameterized by ``learner_id`` from day one (hardcoded to
"artem" in this phase). Old src/spanish_vibes/ tree is not touched.
"""

from __future__ import annotations

import re
import secrets
import unicodedata
from pathlib import Path
from typing import Any

import json
import random

import anthropic

from .database import (
    get_all_words,
    get_grammar_status,
    get_learner_summary,
    get_or_create_learner,
    get_words_due,
    init_db,
    track_word,
    update_grammar_status,
    update_learner_profile,
)
from .placement_questions import QUESTION_BANK, PlacementQuestion, level_to_cefr
from dotenv import load_dotenv
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from jinja2 import Environment, FileSystemLoader, select_autoescape

load_dotenv(override=True)  # picks up app/.env, overrides any pre-set env vars

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

LEARNER_ID = "artem"  # Phase 1: single user. Multi-user lookup goes here later.
MODEL = "claude-opus-4-7"
MAX_TOKENS = 2048
TRANSLATE_MODEL = "claude-haiku-4-5-20251001"

APP_DIR = Path(__file__).parent
FRAMEWORK_PATH = APP_DIR / "tutor_framework.md"
PERSONA_PATH = APP_DIR / "personas" / "marta.md"
MEMORY_DIR = APP_DIR / "memory"


def memory_path(learner_id: str) -> Path:
    return MEMORY_DIR / learner_id / "learner.md"


# ---------------------------------------------------------------------------
# Anthropic client + tool definitions
# ---------------------------------------------------------------------------

client = anthropic.Anthropic()  # picks up ANTHROPIC_API_KEY

TOOLS = [
    {
        "name": "create_fill_in_blank",
        "description": (
            "Drop a tiny inline fill-in-the-blank exercise into the chat. Use "
            "sparingly — at most once per few exchanges, only when something "
            "the learner just said makes a contextual exercise feel natural. "
            "Each item should test one missing word from a short Spanish "
            "sentence, ideally tied to what was just discussed."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "intro": {
                    "type": "string",
                    "description": (
                        "One sentence in your voice (Spanish), introducing the "
                        "exercise as you'd hand it to them."
                    ),
                },
                "sentences": {
                    "type": "array",
                    "minItems": 2,
                    "maxItems": 4,
                    "items": {
                        "type": "object",
                        "properties": {
                            "text_with_blank": {
                                "type": "string",
                                "description": (
                                    "Spanish sentence with a single ___ where "
                                    "the missing word goes."
                                ),
                            },
                            "answer": {
                                "type": "string",
                                "description": "The single correct word.",
                            },
                            "hint": {
                                "type": "string",
                                "description": (
                                    "Optional short English hint, e.g. "
                                    "'(to have, yo form)'."
                                ),
                            },
                        },
                        "required": ["text_with_blank", "answer"],
                    },
                },
            },
            "required": ["intro", "sentences"],
        },
    },
    {
        "name": "create_multiple_choice",
        "description": (
            "Drop a multiple-choice question into the chat. Great for testing "
            "vocabulary, grammar, or comprehension. One question per call."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "intro": {
                    "type": "string",
                    "description": "One sentence in your voice (Spanish) setting up the question.",
                },
                "question": {
                    "type": "string",
                    "description": "The question (Spanish or English depending on what you're testing).",
                },
                "options": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 4,
                    "maxItems": 4,
                    "description": "Four answer options. Exactly one must be correct.",
                },
                "correct_index": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 3,
                    "description": "Index (0-3) of the correct option.",
                },
                "explanation": {
                    "type": "string",
                    "description": "Brief explanation shown after the learner answers.",
                },
            },
            "required": [
                "intro",
                "question",
                "options",
                "correct_index",
                "explanation",
            ],
        },
    },
    {
        "name": "create_flashcard_set",
        "description": (
            "Show a set of 3-6 vocabulary flashcards inline. Spanish on front, "
            "English on back. Use to introduce new words or review vocabulary "
            "from the conversation."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "intro": {
                    "type": "string",
                    "description": "One sentence intro in your voice (Spanish).",
                },
                "cards": {
                    "type": "array",
                    "minItems": 3,
                    "maxItems": 6,
                    "items": {
                        "type": "object",
                        "properties": {
                            "front": {
                                "type": "string",
                                "description": "Spanish word or short phrase.",
                            },
                            "back": {
                                "type": "string",
                                "description": "English translation.",
                            },
                            "example": {
                                "type": "string",
                                "description": "Optional example sentence in Spanish.",
                            },
                        },
                        "required": ["front", "back"],
                    },
                },
            },
            "required": ["intro", "cards"],
        },
    },
    {
        "name": "create_grammar_note",
        "description": (
            "Show a concise grammar explanation card inline. Use when the "
            "learner keeps making the same mistake, asks about a rule, or "
            "when a grammar point would help them level up."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Grammar topic, e.g. 'Ser vs Estar'.",
                },
                "explanation": {
                    "type": "string",
                    "description": "Plain-language explanation in English. 1-3 sentences.",
                },
                "examples": {
                    "type": "array",
                    "minItems": 2,
                    "maxItems": 4,
                    "items": {
                        "type": "object",
                        "properties": {
                            "spanish": {"type": "string"},
                            "english": {"type": "string"},
                        },
                        "required": ["spanish", "english"],
                    },
                },
            },
            "required": ["title", "explanation", "examples"],
        },
    },
    {
        "name": "create_quiz_set",
        "description": (
            "Drop a rapid-fire drill set of 5-8 multiple-choice questions. "
            "Duolingo-style: the learner powers through them one by one, "
            "wrong answers come back at the end for a retry. Use when the "
            "learner wants to be drilled/tested, or you want to give them "
            "a proper practice session. Keep all questions on one topic or "
            "closely related topics. For beginners, test basic vocabulary "
            "and simple grammar — not advanced stuff."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "intro": {
                    "type": "string",
                    "description": "One sentence in your voice (Spanish) introducing the drill.",
                },
                "topic": {
                    "type": "string",
                    "description": "Short label for the topic, e.g. 'Colores' or 'Ser vs Estar'.",
                },
                "questions": {
                    "type": "array",
                    "minItems": 5,
                    "maxItems": 8,
                    "items": {
                        "type": "object",
                        "properties": {
                            "question": {
                                "type": "string",
                                "description": "The question text.",
                            },
                            "options": {
                                "type": "array",
                                "items": {"type": "string"},
                                "minItems": 4,
                                "maxItems": 4,
                                "description": "Four answer options.",
                            },
                            "correct_index": {
                                "type": "integer",
                                "minimum": 0,
                                "maximum": 3,
                                "description": "Index (0-3) of the correct option.",
                            },
                        },
                        "required": ["question", "options", "correct_index"],
                    },
                },
            },
            "required": ["intro", "topic", "questions"],
        },
    },
    {
        "name": "run_placement_test",
        "description": (
            "Run an adaptive placement test to assess the learner's CEFR level. "
            "Use this at the start of a first session when you have no learner "
            "notes yet, or when the learner explicitly asks to find out their "
            "level (e.g. 'what level am I?', 'test my level', 'placement test'). "
            "The test is 12 adaptive multiple-choice questions that hone in on "
            "their level using a binary-search approach. Do NOT use this for "
            "regular quizzing — use create_quiz_set for that."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": (
                        "Brief explanation of why you're running the placement "
                        "test, e.g. 'First session, no notes' or 'Learner asked "
                        "to check their level'."
                    ),
                },
            },
            "required": ["reason"],
        },
    },
    {
        "name": "save_learner_notes",
        "description": (
            "Save your full markdown notes about this learner to disk. Call "
            "at the end of a session (when they say bye or trail off). Include "
            "everything worth keeping for next time — facts, struggles, plans."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "notes": {
                    "type": "string",
                    "description": "Full markdown body. Overwrites the file.",
                },
            },
            "required": ["notes"],
        },
    },
]


# ---------------------------------------------------------------------------
# Persona + memory
# ---------------------------------------------------------------------------


def build_system_prompt(learner_id: str) -> str:
    notes_path = memory_path(learner_id)
    freeform_notes = (
        notes_path.read_text()
        if notes_path.exists()
        else "_(no notes yet — first session)_"
    )
    # Build combined learner context: structured DB data + freeform notes
    structured = get_learner_summary(learner_id)
    if structured:
        combined_notes = structured + "\n\n---\n\n## Freeform notes\n" + freeform_notes
    else:
        combined_notes = freeform_notes
    framework = FRAMEWORK_PATH.read_text().replace("{learner_notes}", combined_notes)
    persona = PERSONA_PATH.read_text()
    return framework + "\n\n---\n\n" + persona


def save_notes(learner_id: str, notes: str) -> None:
    path = memory_path(learner_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(notes)


# ---------------------------------------------------------------------------
# In-memory session state (single user, single process — Phase 1)
# ---------------------------------------------------------------------------

# Conversation history per learner (Anthropic message-list format)
HISTORY: dict[str, list[dict[str, Any]]] = {LEARNER_ID: []}

# Pending quizzes: card_id -> {"sentences": [...], "blanks_remaining": int, "results": [...]}
QUIZZES: dict[str, dict[str, Any]] = {}

# Translation cache: "word|||context" -> translation string
_translate_cache: dict[str, str] = {}


# ---------------------------------------------------------------------------
# Placement test helpers
# ---------------------------------------------------------------------------

PLACEMENT_TOTAL = 12  # number of questions in a placement test


def pick_placement_question(
    difficulty: float, asked_indices: set[int]
) -> tuple[int, PlacementQuestion] | None:
    """Pick the closest question to *difficulty* that hasn't been asked yet."""
    candidates = [(i, q) for i, q in enumerate(QUESTION_BANK) if i not in asked_indices]
    if not candidates:
        return None
    # Sort by distance to target difficulty, break ties randomly
    candidates.sort(key=lambda pair: (abs(pair[1].level - difficulty), random.random()))
    return candidates[0]


def compute_placement_result(quiz: dict[str, Any]) -> dict[str, Any]:
    """Compute the final placement result from a completed quiz."""
    results = quiz["results"]
    # Group results by level label
    level_buckets: dict[str, dict[str, int]] = {}
    for r in results:
        label = r["level_label"]
        if label not in level_buckets:
            level_buckets[label] = {"correct": 0, "total": 0}
        level_buckets[label]["total"] += 1
        if r["correct"]:
            level_buckets[label]["correct"] += 1

    # Estimated level = average difficulty of correctly answered questions
    correct_levels = [r["level"] for r in results if r["correct"]]
    if correct_levels:
        avg_correct = sum(correct_levels) / len(correct_levels)
    else:
        avg_correct = 0.0
    estimated_level = level_to_cefr(avg_correct)

    # Build breakdown for display (ordered by level)
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

    # Identify grammar gaps (topics the learner got wrong)
    gaps = []
    for r in results:
        if not r["correct"] and r["grammar_topic"] not in gaps:
            gaps.append(r["grammar_topic"])

    # Build text summary for the agent
    parts = []
    for b in breakdown:
        parts.append(f"{b['correct']}/{b['total']} {b['label']} correct")
    gap_str = ", ".join(gaps) if gaps else "none identified"
    summary_text = (
        f"[Placement test complete: estimated level {estimated_level}. "
        f"Breakdown: {'; '.join(parts)}. "
        f"Grammar gaps: {gap_str}.]"
    )

    return {
        "level": estimated_level,
        "breakdown": breakdown,
        "gaps": gaps,
        "summary_text": summary_text,
    }


# ---------------------------------------------------------------------------
# Agent loop
# ---------------------------------------------------------------------------


def _persona_blocks_for(rendered_cards: list[dict[str, Any]]) -> str:
    return ""  # placeholder for future inline data injection if needed


def run_agent_turn(learner_id: str, user_text: str | None) -> dict[str, Any]:
    """Run one user-turn through Claude.

    If ``user_text`` is None, this is a continuation turn (e.g. after a quiz
    completes) and we just call the model on the existing history.

    Returns:
        {"text": str, "cards": [...]}  — text is the persona's chat reply,
        cards is a list of inline cards Claude rendered via tools (each is
        a dict with "type", "id", "intro", "sentences", and the answers
        already removed from the client-facing payload).
    """
    history = HISTORY[learner_id]
    if user_text is not None:
        history.append({"role": "user", "content": user_text})

    rendered_cards: list[dict[str, Any]] = []
    system = build_system_prompt(learner_id)

    while True:
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=[
                {
                    "type": "text",
                    "text": system,
                    "cache_control": {"type": "ephemeral"},
                }
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
            # pause_turn / refusal / max_tokens — treat as terminal for Phase 1
            history.append({"role": "assistant", "content": response.content})
            text = "".join(b.text for b in response.content if b.type == "text").strip()
            return {"text": text or "…", "cards": rendered_cards}

        # tool_use: execute every tool call, append results, loop
        history.append({"role": "assistant", "content": response.content})
        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
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
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": (
                            f"Exercise rendered with {len(sentences)} blanks. "
                            "The learner is working through them now — you'll get "
                            "their results in a follow-up message."
                        ),
                    }
                )
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
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": "Multiple-choice question rendered. Waiting for answer.",
                    }
                )
            elif block.name == "create_flashcard_set":
                rendered_cards.append(
                    {
                        "type": "flashcard_set",
                        "id": secrets.token_urlsafe(8),
                        "intro": block.input["intro"],
                        "cards": block.input["cards"],
                    }
                )
                # Track flashcard words for spaced repetition
                for fc in block.input["cards"]:
                    track_word(
                        learner_id,
                        word=fc["front"],
                        translation=fc["back"],
                        domain=None,
                    )
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": (
                            f"Flashcard set with {len(block.input['cards'])} cards "
                            "rendered. The learner is reviewing them now."
                        ),
                    }
                )
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
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": "Grammar note rendered.",
                    }
                )
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
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": (
                            f"Quiz set with {len(questions)} questions rendered. "
                            "The learner is working through them now — you'll get "
                            "a summary when they finish."
                        ),
                    }
                )
            elif block.name == "run_placement_test":
                card_id = secrets.token_urlsafe(8)
                difficulty = 2.0  # start at A2
                first_pick = pick_placement_question(difficulty, set())
                if first_pick is None:
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": "Error: no questions available.",
                            "is_error": True,
                        }
                    )
                    continue
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
                        "intro": (
                            "Let's see where you are! "
                            "12 quick questions — just pick the best answer."
                        ),
                        "question": {
                            "question": q.question,
                            "options": q.options,
                        },
                        "current": 1,
                        "total": PLACEMENT_TOTAL,
                    }
                )
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": (
                            f"Placement test started ({PLACEMENT_TOTAL} questions). "
                            "The learner is working through it now — you'll get "
                            "the result when they finish."
                        ),
                    }
                )
            elif block.name == "save_learner_notes":
                notes_text = block.input["notes"]
                save_notes(learner_id, notes_text)
                # Parse structured info from notes and update DB
                _sync_notes_to_db(learner_id, notes_text)
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": "Notes saved to disk and learner profile updated.",
                    }
                )
            else:
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": f"Unknown tool: {block.name}",
                        "is_error": True,
                    }
                )
        history.append({"role": "user", "content": tool_results})


# ---------------------------------------------------------------------------
# Answer comparison
# ---------------------------------------------------------------------------


def normalize(s: str) -> str:
    s = unicodedata.normalize("NFD", s.lower().strip())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s)


def is_correct(user_answer: str, correct_answer: str) -> bool:
    return normalize(user_answer) == normalize(correct_answer)


# ---------------------------------------------------------------------------
# Database sync helpers
# ---------------------------------------------------------------------------


def _sync_notes_to_db(learner_id: str, notes_md: str) -> None:
    """Parse structured info from Marta's markdown notes and update the DB."""
    updates: dict[str, Any] = {"notes_md": notes_md}

    # Extract CEFR level (patterns like "A1", "A2", "B1", "B2")
    cefr_match = re.search(r"\b(A1|A2|B1|B2)\b", notes_md)
    if cefr_match:
        updates["cefr_level"] = cefr_match.group(1)

    # Extract interests from "About them" section if present
    about_match = re.search(
        r"##\s*About\s+them\s*\n(.*?)(?=\n##|\Z)",
        notes_md,
        re.DOTALL | re.IGNORECASE,
    )
    if about_match:
        about_text = about_match.group(1).strip()
        interests: list[str] = []
        # Try explicit "interests: X, Y" pattern first
        interest_match = re.search(
            r"interests?[:\s]+(.+?)(?:\n|$)",
            about_text,
            re.IGNORECASE,
        )
        if interest_match:
            raw = interest_match.group(1)
            interests = [i.strip().strip(".-*") for i in raw.split(",") if i.strip()]
        else:
            # Fall back: extract topics from "loves/enjoys/likes X and Y" patterns
            love_match = re.findall(
                r"(?:loves?|enjoys?|likes?|interested in|into)\s+(.+?)(?:\n|$)",
                about_text,
                re.IGNORECASE,
            )
            for raw in love_match:
                # Split on " and " and commas
                for part in re.split(r"\s+and\s+|,\s*", raw):
                    cleaned = part.strip().strip(".-*")
                    if cleaned and len(cleaned) < 50:
                        interests.append(cleaned)
        if interests:
            updates["interests"] = json.dumps(interests)

    update_learner_profile(learner_id, **updates)


def _track_quiz_grammar(learner_id: str, topic: str, correct: int, total: int) -> None:
    """Update grammar_status based on quiz set results."""
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
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI()

# Initialize the database on startup
init_db()
get_or_create_learner(LEARNER_ID)

app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")

# cache_size=0 sidesteps a Jinja2 3.1.6 LRU bug on Python 3.14.
_jinja_env = Environment(
    loader=FileSystemLoader(APP_DIR / "templates"),
    autoescape=select_autoescape(["html"]),
    cache_size=0,
)
templates = Jinja2Templates(env=_jinja_env)


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request, "index.html")


@app.post("/chat", response_class=HTMLResponse)
def chat(request: Request, message: str = Form(...)):
    """Send a user message, get back HTML fragments to append to #chat."""
    text = message.strip()
    if not text:
        return HTMLResponse("")
    result = run_agent_turn(LEARNER_ID, text)
    return templates.TemplateResponse(
        request,
        "partials/turn.html",
        {
            "user_text": text,
            "persona_text": result["text"],
            "cards": result["cards"],
        },
    )


@app.post("/quiz/answer", response_class=HTMLResponse)
def quiz_answer(
    request: Request,
    card_id: str = Form(...),
    blank_idx: int = Form(...),
    user_answer: str = Form(...),
):
    quiz = QUIZZES.get(card_id)
    if quiz is None:
        return HTMLResponse("<div>(quiz expired)</div>")
    sentence = quiz["sentences"][blank_idx]
    correct = is_correct(user_answer, sentence["answer"])
    quiz["results"].append(
        {
            "blank_idx": blank_idx,
            "user_answer": user_answer,
            "correct_answer": sentence["answer"],
            "correct": correct,
        }
    )
    quiz["blanks_remaining"] -= 1
    last = quiz["blanks_remaining"] == 0
    return templates.TemplateResponse(
        request,
        "partials/quiz_feedback.html",
        {
            "card_id": card_id,
            "blank_idx": blank_idx,
            "user_answer": user_answer,
            "correct": correct,
            "correct_answer": sentence["answer"],
            "last": last,
        },
    )


@app.post("/quiz/mcq", response_class=HTMLResponse)
def quiz_mcq(
    request: Request,
    card_id: str = Form(...),
    selected: int = Form(...),
):
    quiz = QUIZZES.get(card_id)
    if quiz is None:
        return HTMLResponse("<div>(quiz expired)</div>")
    correct = selected == quiz["correct_index"]
    quiz["result"] = {"correct": correct, "selected": selected}
    return templates.TemplateResponse(
        request,
        "partials/mcq_feedback.html",
        {
            "card_id": card_id,
            "correct": correct,
            "explanation": quiz["explanation"],
            "correct_index": quiz["correct_index"],
            "selected": selected,
        },
    )


@app.post("/quiz/set/answer", response_class=HTMLResponse)
def quiz_set_answer(
    request: Request,
    card_id: str = Form(...),
    selected: int = Form(...),
):
    quiz = QUIZZES.get(card_id)
    if quiz is None:
        return HTMLResponse("<div>(quiz expired)</div>")
    q = quiz["questions"][quiz["current_index"]]
    correct = selected == q["correct_index"]
    is_retry = q.get("is_retry", False)
    quiz["results"].append({"correct": correct, "question": q["question"]})
    if not correct and not is_retry:
        quiz["questions"].append({**q, "is_retry": True})
    quiz["current_index"] += 1
    has_next = quiz["current_index"] < len(quiz["questions"])
    return templates.TemplateResponse(
        request,
        "partials/quiz_set_feedback.html",
        {
            "card_id": card_id,
            "correct": correct,
            "correct_answer": q["options"][q["correct_index"]],
            "selected_answer": q["options"][selected],
            "has_next": has_next,
            "is_retry": is_retry,
        },
    )


@app.post("/quiz/set/next", response_class=HTMLResponse)
def quiz_set_next(request: Request, card_id: str = Form(...)):
    quiz = QUIZZES.get(card_id)
    if quiz is None:
        return HTMLResponse("<div>(quiz expired)</div>")
    idx = quiz["current_index"]
    if idx >= len(quiz["questions"]):
        correct_count = sum(1 for r in quiz["results"] if r["correct"])
        total = quiz["original_count"]
        return templates.TemplateResponse(
            request,
            "partials/quiz_set_summary.html",
            {
                "card_id": card_id,
                "correct_count": correct_count,
                "total": total,
            },
        )
    q = quiz["questions"][idx]
    return templates.TemplateResponse(
        request,
        "partials/quiz_set_question.html",
        {
            "card_id": card_id,
            "question": q,
            "current": idx + 1,
            "total": len(quiz["questions"]),
            "is_retry": q.get("is_retry", False),
        },
    )


@app.post("/quiz/complete", response_class=HTMLResponse)
def quiz_complete(request: Request, card_id: str = Form(...)):
    quiz = QUIZZES.pop(card_id, None)
    if quiz is None:
        return HTMLResponse("")

    if quiz.get("type") == "quiz_set":
        correct_count = sum(1 for r in quiz["results"] if r["correct"])
        total = quiz["original_count"]
        retries = len(quiz["questions"]) - quiz["original_count"]
        summary = (
            f"[Quiz set complete: {correct_count}/{total} correct"
            f"{f', {retries} retry questions needed' if retries else ''}. "
            "React to how they did — brief, in character.]"
        )
        # Track grammar status based on quiz results
        topic = quiz.get("topic", "")
        if topic:
            _track_quiz_grammar(LEARNER_ID, topic, correct_count, total)
    elif quiz.get("type") == "mcq":
        r = quiz.get("result", {})
        summary = (
            f"[MCQ result: {'correct' if r.get('correct') else 'wrong'}. "
            "React naturally, briefly.]"
        )
    else:
        correct_count = sum(1 for r in quiz["results"] if r["correct"])
        total = len(quiz["sentences"])
        misses = [
            f"wrote '{r['user_answer']}' for '{r['correct_answer']}'"
            for r in quiz["results"]
            if not r["correct"]
        ]
        summary = f"[Exercise complete: {correct_count}/{total} correct"
        if misses:
            summary += f". Misses: {'; '.join(misses)}"
        summary += ". React to how the learner did, in character.]"

    result = run_agent_turn(LEARNER_ID, summary)
    return templates.TemplateResponse(
        request,
        "partials/persona_msg.html",
        {"persona_text": result["text"]},
    )


# ---------------------------------------------------------------------------
# Placement test endpoints
# ---------------------------------------------------------------------------


@app.post("/placement/answer", response_class=HTMLResponse)
def placement_answer(
    request: Request,
    card_id: str = Form(...),
    selected: int = Form(...),
):
    quiz = QUIZZES.get(card_id)
    if quiz is None:
        return HTMLResponse("<div>(quiz expired)</div>")

    q: PlacementQuestion = quiz["current_question"]
    correct = selected == q.correct_index

    # Record result
    quiz["results"].append(
        {
            "correct": correct,
            "level": q.level,
            "level_label": q.level_label,
            "grammar_topic": q.grammar_topic,
            "question": q.question,
        }
    )

    # Adapt difficulty
    if correct:
        quiz["difficulty"] = min(quiz["difficulty"] + 0.5, 5.0)
    else:
        quiz["difficulty"] = max(quiz["difficulty"] - 0.5, 0.0)

    quiz["current_index"] += 1
    has_next = quiz["current_index"] < quiz["total"]

    return templates.TemplateResponse(
        request,
        "partials/placement_feedback.html",
        {
            "card_id": card_id,
            "correct": correct,
            "correct_answer": q.options[q.correct_index],
            "selected_answer": q.options[selected],
            "has_next": has_next,
        },
    )


@app.post("/placement/next", response_class=HTMLResponse)
def placement_next(request: Request, card_id: str = Form(...)):
    quiz = QUIZZES.get(card_id)
    if quiz is None:
        return HTMLResponse("<div>(quiz expired)</div>")

    idx = quiz["current_index"]
    if idx >= quiz["total"]:
        # Test complete -- show result
        result = compute_placement_result(quiz)
        return templates.TemplateResponse(
            request,
            "partials/placement_result.html",
            {
                "card_id": card_id,
                "level": result["level"],
                "breakdown": result["breakdown"],
                "gaps": result["gaps"],
            },
        )

    # Pick next question adaptively
    asked = set(quiz["asked_indices"])
    pick = pick_placement_question(quiz["difficulty"], asked)
    if pick is None:
        # Ran out of questions -- finish early
        result = compute_placement_result(quiz)
        return templates.TemplateResponse(
            request,
            "partials/placement_result.html",
            {
                "card_id": card_id,
                "level": result["level"],
                "breakdown": result["breakdown"],
                "gaps": result["gaps"],
            },
        )

    q_idx, q = pick
    quiz["asked_indices"].append(q_idx)
    quiz["current_question"] = q

    return templates.TemplateResponse(
        request,
        "partials/placement_question.html",
        {
            "card_id": card_id,
            "question": {"question": q.question, "options": q.options},
            "current": idx + 1,
            "total": quiz["total"],
        },
    )


@app.post("/placement/complete", response_class=HTMLResponse)
def placement_complete(request: Request, card_id: str = Form(...)):
    quiz = QUIZZES.pop(card_id, None)
    if quiz is None:
        return HTMLResponse("")

    result = compute_placement_result(quiz)

    # Persist the placement level and grammar gaps to the DB
    update_learner_profile(LEARNER_ID, cefr_level=result["level"])
    for gap in result.get("gaps", []):
        update_grammar_status(LEARNER_ID, gap, "gap")

    summary = result["summary_text"]
    agent_result = run_agent_turn(LEARNER_ID, summary)
    return templates.TemplateResponse(
        request,
        "partials/persona_msg.html",
        {"persona_text": agent_result["text"]},
    )


@app.post("/translate")
def translate(text: str = Form(...), context: str = Form("")):
    text = text.strip()
    if not text:
        return {"translation": ""}
    cache_key = f"{text}|||{context}"
    if cache_key in _translate_cache:
        return {"translation": _translate_cache[cache_key]}
    resp = client.messages.create(
        model=TRANSLATE_MODEL,
        max_tokens=100,
        messages=[
            {
                "role": "user",
                "content": (
                    "Translate this Spanish to English. Reply with ONLY the "
                    "English translation, nothing else. Be brief.\n\n"
                    f"Spanish: {text}"
                    + (f"\nSentence context: {context}" if context else "")
                ),
            }
        ],
    )
    translation = resp.content[0].text.strip()
    _translate_cache[cache_key] = translation
    return {"translation": translation}


@app.get("/learner/stats")
def learner_stats():
    """JSON summary of the learner's profile, grammar, and word tracking."""
    profile = get_or_create_learner(LEARNER_ID)
    grammar = get_grammar_status(LEARNER_ID)
    words = get_all_words(LEARNER_ID)
    due = get_words_due(LEARNER_ID)

    interests = None
    if profile.get("interests"):
        try:
            interests = json.loads(profile["interests"])
        except (json.JSONDecodeError, TypeError):
            interests = None

    return JSONResponse(
        {
            "learner_id": LEARNER_ID,
            "profile": {
                "display_name": profile.get("display_name"),
                "cefr_level": profile.get("cefr_level"),
                "interests": interests,
                "created_at": profile.get("created_at"),
                "updated_at": profile.get("updated_at"),
            },
            "grammar": {
                topic: {
                    "status": info["status"],
                    "last_tested": info["last_tested"],
                    "evidence_count": len(info["evidence"]),
                }
                for topic, info in grammar.items()
            },
            "vocabulary": {
                "total_words": len(words),
                "words_due": len(due),
                "due_words": [
                    {"word": w["word"], "translation": w["translation"]} for w in due
                ],
            },
            "word_details": [
                {
                    "word": w["word"],
                    "translation": w["translation"],
                    "domain": w["domain"],
                    "repetitions": w["repetitions"],
                    "ease_factor": round(w["ease_factor"], 2),
                    "interval_days": round(w["interval_days"], 1),
                    "times_correct": w["times_correct"],
                    "times_wrong": w["times_wrong"],
                    "next_review": w["next_review"],
                }
                for w in words
            ],
        }
    )


@app.get("/healthz")
def healthz():
    return {"ok": True, "model": MODEL, "learner_id": LEARNER_ID}
