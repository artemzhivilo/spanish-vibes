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

import anthropic
from dotenv import load_dotenv
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse
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

APP_DIR = Path(__file__).parent
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
    template = PERSONA_PATH.read_text()
    notes_path = memory_path(learner_id)
    notes = (
        notes_path.read_text()
        if notes_path.exists()
        else "_(no notes yet — first session)_"
    )
    return template.replace("{learner_notes}", notes)


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
            elif block.name == "save_learner_notes":
                save_notes(learner_id, block.input["notes"])
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": "Notes saved to disk.",
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
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI()
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


@app.post("/quiz/complete", response_class=HTMLResponse)
def quiz_complete(request: Request, card_id: str = Form(...)):
    quiz = QUIZZES.pop(card_id, None)
    if quiz is None:
        return HTMLResponse("")

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


@app.get("/healthz")
def healthz():
    return {"ok": True, "model": MODEL, "learner_id": LEARNER_ID}
