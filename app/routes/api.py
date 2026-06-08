"""JSON API routes for the SvelteKit frontend.

These mirror the existing HTMX routes but return JSON instead of HTML,
so the SvelteKit frontend can consume them.
"""

from __future__ import annotations

import re
import unicodedata

import anthropic
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..agent import (
    compute_placement_result,
    pick_placement_question,
    run_agent_turn,
    track_quiz_grammar,
)
from ..config import LEARNER_ID, PERSONA_REGISTRY, TRANSLATE_MODEL
from ..database import (
    append_chat_log,
    get_all_words,
    get_chat_log,
    get_grammar_status,
    get_or_create_learner,
    get_words_due,
    update_grammar_status,
    update_learner_profile,
)
from ..state import ACTIVE_PERSONA, QUIZZES

router = APIRouter(prefix="/api")

_translate_client = anthropic.Anthropic()
_translate_cache: dict[str, str] = {}


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class ChatRequest(BaseModel):
    message: str


class QuizAnswerRequest(BaseModel):
    card_id: str
    blank_idx: int
    answer: str


class McqAnswerRequest(BaseModel):
    card_id: str
    selected: int


class QuizSetAnswerRequest(BaseModel):
    card_id: str
    selected: int


class QuizSetNextRequest(BaseModel):
    card_id: str


class QuizCompleteRequest(BaseModel):
    card_id: str


class PersonaSwitchRequest(BaseModel):
    persona_id: str


class TranslateRequest(BaseModel):
    text: str
    context: str = ""


class PlacementAnswerRequest(BaseModel):
    card_id: str
    selected: int


class PlacementNextRequest(BaseModel):
    card_id: str


class PlacementCompleteRequest(BaseModel):
    card_id: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _normalize(s: str) -> str:
    s = unicodedata.normalize("NFD", s.lower().strip())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s)


def _is_correct(user_answer: str, correct_answer: str) -> bool:
    return _normalize(user_answer) == _normalize(correct_answer)


def _persona_json(persona_id: str) -> dict:
    info = PERSONA_REGISTRY.get(persona_id, PERSONA_REGISTRY["marta"])
    return {"id": persona_id, **info}


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------


@router.post("/chat")
def api_chat(req: ChatRequest):
    text = req.message.strip()
    if not text:
        return JSONResponse(
            {"text": "", "cards": [], "persona": _persona_json("marta")}
        )

    persona_id = ACTIVE_PERSONA.get(LEARNER_ID, "marta")
    result = run_agent_turn(LEARNER_ID, text, persona_id)

    # Persist to DB
    append_chat_log(LEARNER_ID, persona_id, "user", text)
    if result["text"]:
        append_chat_log(LEARNER_ID, persona_id, "persona", result["text"])

    return JSONResponse(
        {
            "text": result["text"],
            "cards": result["cards"],
            "persona": _persona_json(persona_id),
        }
    )


@router.get("/chat/history")
def api_chat_history():
    persona_id = ACTIVE_PERSONA.get(LEARNER_ID, "marta")
    log = get_chat_log(LEARNER_ID, persona_id)
    return JSONResponse(
        {
            "messages": log,
            "persona": _persona_json(persona_id),
        }
    )


# ---------------------------------------------------------------------------
# Quiz / Fill-in-blank
# ---------------------------------------------------------------------------


@router.post("/quiz/answer")
def api_quiz_answer(req: QuizAnswerRequest):
    quiz = QUIZZES.get(req.card_id)
    if quiz is None:
        return JSONResponse({"error": "quiz expired"}, status_code=404)

    sentence = quiz["sentences"][req.blank_idx]
    correct = _is_correct(req.answer, sentence["answer"])
    quiz["results"].append(
        {
            "blank_idx": req.blank_idx,
            "user_answer": req.answer,
            "correct_answer": sentence["answer"],
            "correct": correct,
        }
    )
    quiz["blanks_remaining"] -= 1

    return JSONResponse(
        {
            "correct": correct,
            "correct_answer": sentence["answer"],
            "last": quiz["blanks_remaining"] == 0,
        }
    )


# ---------------------------------------------------------------------------
# MCQ
# ---------------------------------------------------------------------------


@router.post("/quiz/mcq")
def api_quiz_mcq(req: McqAnswerRequest):
    quiz = QUIZZES.get(req.card_id)
    if quiz is None:
        return JSONResponse({"error": "quiz expired"}, status_code=404)

    correct = req.selected == quiz["correct_index"]
    quiz["result"] = {"correct": correct, "selected": req.selected}

    return JSONResponse(
        {
            "correct": correct,
            "explanation": quiz["explanation"],
            "correct_index": quiz["correct_index"],
            "selected": req.selected,
        }
    )


# ---------------------------------------------------------------------------
# Quiz Set
# ---------------------------------------------------------------------------


@router.post("/quiz/set/answer")
def api_quiz_set_answer(req: QuizSetAnswerRequest):
    quiz = QUIZZES.get(req.card_id)
    if quiz is None:
        return JSONResponse({"error": "quiz expired"}, status_code=404)

    q = quiz["questions"][quiz["current_index"]]
    correct = req.selected == q["correct_index"]
    is_retry = q.get("is_retry", False)
    quiz["results"].append({"correct": correct, "question": q["question"]})

    if not correct and not is_retry:
        quiz["questions"].append({**q, "is_retry": True})

    quiz["current_index"] += 1
    has_next = quiz["current_index"] < len(quiz["questions"])

    return JSONResponse(
        {
            "correct": correct,
            "correct_answer": q["options"][q["correct_index"]],
            "selected_answer": q["options"][req.selected],
            "has_next": has_next,
            "is_retry": is_retry,
        }
    )


@router.post("/quiz/set/next")
def api_quiz_set_next(req: QuizSetNextRequest):
    quiz = QUIZZES.get(req.card_id)
    if quiz is None:
        return JSONResponse({"error": "quiz expired"}, status_code=404)

    idx = quiz["current_index"]
    if idx >= len(quiz["questions"]):
        correct_count = sum(1 for r in quiz["results"] if r["correct"])
        total = quiz["original_count"]
        return JSONResponse(
            {
                "complete": True,
                "correct_count": correct_count,
                "total": total,
            }
        )

    q = quiz["questions"][idx]
    return JSONResponse(
        {
            "complete": False,
            "question": q,
            "current": idx + 1,
            "total": len(quiz["questions"]),
            "is_retry": q.get("is_retry", False),
        }
    )


# ---------------------------------------------------------------------------
# Quiz Complete (triggers agent reaction)
# ---------------------------------------------------------------------------


@router.post("/quiz/complete")
def api_quiz_complete(req: QuizCompleteRequest):
    quiz = QUIZZES.pop(req.card_id, None)
    if quiz is None:
        return JSONResponse(
            {"text": "", "cards": [], "persona": _persona_json("marta")}
        )

    # Build summary for the agent
    if quiz.get("type") == "quiz_set":
        correct_count = sum(1 for r in quiz["results"] if r["correct"])
        total = quiz["original_count"]
        retries = len(quiz["questions"]) - quiz["original_count"]
        summary = (
            f"[Quiz set complete: {correct_count}/{total} correct"
            f"{f', {retries} retry questions needed' if retries else ''}. "
            "React to how they did — brief, in character.]"
        )
        topic = quiz.get("topic", "")
        if topic:
            track_quiz_grammar(LEARNER_ID, topic, correct_count, total)
    elif quiz.get("type") == "mcq":
        r = quiz.get("result", {})
        summary = f"[MCQ result: {'correct' if r.get('correct') else 'wrong'}. React naturally, briefly.]"
    elif quiz.get("type") == "placement":
        result = compute_placement_result(quiz)
        update_learner_profile(LEARNER_ID, cefr_level=result["level"])
        for gap in result.get("gaps", []):
            update_grammar_status(LEARNER_ID, gap, "gap")
        summary = result["summary_text"]
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

    persona_id = ACTIVE_PERSONA.get(LEARNER_ID, "marta")
    result = run_agent_turn(LEARNER_ID, summary, persona_id)

    if result["text"]:
        append_chat_log(LEARNER_ID, persona_id, "persona", result["text"])

    return JSONResponse(
        {
            "text": result["text"],
            "cards": result["cards"],
            "persona": _persona_json(persona_id),
        }
    )


# ---------------------------------------------------------------------------
# Placement Test
# ---------------------------------------------------------------------------


@router.post("/placement/answer")
def api_placement_answer(req: PlacementAnswerRequest):
    quiz = QUIZZES.get(req.card_id)
    if quiz is None:
        return JSONResponse({"error": "quiz expired"}, status_code=404)

    q = quiz["current_question"]
    correct = req.selected == q.correct_index

    quiz["results"].append(
        {
            "correct": correct,
            "level": q.level,
            "level_label": q.level_label,
            "grammar_topic": q.grammar_topic,
            "question": q.question,
        }
    )

    if correct:
        quiz["difficulty"] = min(quiz["difficulty"] + 0.5, 5.0)
    else:
        quiz["difficulty"] = max(quiz["difficulty"] - 0.5, 0.0)

    quiz["current_index"] += 1
    has_next = quiz["current_index"] < quiz["total"]

    return JSONResponse(
        {
            "correct": correct,
            "correct_answer": q.options[q.correct_index],
            "selected_answer": q.options[req.selected],
            "has_next": has_next,
        }
    )


@router.post("/placement/next")
def api_placement_next(req: PlacementNextRequest):
    quiz = QUIZZES.get(req.card_id)
    if quiz is None:
        return JSONResponse({"error": "quiz expired"}, status_code=404)

    idx = quiz["current_index"]
    if idx >= quiz["total"]:
        result = compute_placement_result(quiz)
        return JSONResponse(
            {
                "complete": True,
                "level": result["level"],
                "breakdown": result["breakdown"],
                "gaps": result["gaps"],
            }
        )

    asked = set(quiz["asked_indices"])
    pick = pick_placement_question(quiz["difficulty"], asked)
    if pick is None:
        result = compute_placement_result(quiz)
        return JSONResponse(
            {
                "complete": True,
                "level": result["level"],
                "breakdown": result["breakdown"],
                "gaps": result["gaps"],
            }
        )

    q_idx, q = pick
    quiz["asked_indices"].append(q_idx)
    quiz["current_question"] = q

    return JSONResponse(
        {
            "complete": False,
            "question": {"question": q.question, "options": q.options},
            "current": idx + 1,
            "total": quiz["total"],
        }
    )


# ---------------------------------------------------------------------------
# Personas
# ---------------------------------------------------------------------------


@router.get("/personas")
def api_personas():
    return JSONResponse(
        {
            "personas": {
                pid: {"id": pid, **info} for pid, info in PERSONA_REGISTRY.items()
            },
            "active": ACTIVE_PERSONA.get(LEARNER_ID, "marta"),
        }
    )


@router.post("/persona/switch")
def api_persona_switch(req: PersonaSwitchRequest):
    if req.persona_id not in PERSONA_REGISTRY:
        return JSONResponse({"error": "Unknown persona"}, status_code=400)
    ACTIVE_PERSONA[LEARNER_ID] = req.persona_id
    return JSONResponse(
        {
            "ok": True,
            "persona": _persona_json(req.persona_id),
        }
    )


@router.get("/persona/current")
def api_persona_current():
    persona_id = ACTIVE_PERSONA.get(LEARNER_ID, "marta")
    return JSONResponse(_persona_json(persona_id))


# ---------------------------------------------------------------------------
# Learner Stats
# ---------------------------------------------------------------------------


@router.get("/learner/stats")
def api_learner_stats():
    import json as _json

    profile = get_or_create_learner(LEARNER_ID)
    grammar = get_grammar_status(LEARNER_ID)
    words = get_all_words(LEARNER_ID)
    due = get_words_due(LEARNER_ID)

    interests = None
    if profile.get("interests"):
        try:
            interests = _json.loads(profile["interests"])
        except (_json.JSONDecodeError, TypeError):
            interests = None

    return JSONResponse(
        {
            "profile": {
                "display_name": profile.get("display_name"),
                "cefr_level": profile.get("cefr_level", "A1"),
                "interests": interests,
            },
            "grammar": {
                topic: {"status": info["status"]} for topic, info in grammar.items()
            },
            "vocabulary": {
                "total": len(words),
                "due": len(due),
            },
            "words": [
                {
                    "word": w["word"],
                    "translation": w["translation"],
                    "domain": w["domain"],
                    "repetitions": w["repetitions"],
                    "times_correct": w["times_correct"],
                    "times_wrong": w["times_wrong"],
                }
                for w in words
            ],
        }
    )


# ---------------------------------------------------------------------------
# Reset Progress
# ---------------------------------------------------------------------------


@router.post("/reset-progress")
def api_reset_progress():
    """Wipe all learner data and in-memory state."""
    from ..database import _connect, _execute

    # Clear DB tables
    with _connect() as conn:
        _execute(conn, "DELETE FROM chat_log WHERE learner_id = ?", (LEARNER_ID,))
        _execute(conn, "DELETE FROM word_tracking WHERE learner_id = ?", (LEARNER_ID,))
        _execute(conn, "DELETE FROM grammar_status WHERE learner_id = ?", (LEARNER_ID,))
        _execute(conn, "DELETE FROM session_log WHERE learner_id = ?", (LEARNER_ID,))
        _execute(
            conn,
            "UPDATE learner_profile SET cefr_level = 'A1', interests = NULL, "
            "notes_md = NULL WHERE learner_id = ?",
            (LEARNER_ID,),
        )

    # Clear in-memory state
    from ..state import HISTORY

    keys_to_delete = [k for k in HISTORY if k[0] == LEARNER_ID]
    for k in keys_to_delete:
        del HISTORY[k]
    QUIZZES.clear()
    ACTIVE_PERSONA[LEARNER_ID] = "tutor"

    return JSONResponse({"ok": True})


# ---------------------------------------------------------------------------
# Translate
# ---------------------------------------------------------------------------


@router.post("/translate")
def api_translate(req: TranslateRequest):
    text = req.text.strip()
    if not text:
        return JSONResponse({"translation": ""})

    cache_key = f"{text}|||{req.context}"
    if cache_key in _translate_cache:
        return JSONResponse({"translation": _translate_cache[cache_key]})

    resp = _translate_client.messages.create(
        model=TRANSLATE_MODEL,
        max_tokens=100,
        messages=[
            {
                "role": "user",
                "content": (
                    "Translate this Spanish to English. Reply with ONLY the "
                    "English translation, nothing else. Be brief.\n\n"
                    f"Spanish: {text}"
                    + (f"\nSentence context: {req.context}" if req.context else "")
                ),
            }
        ],
    )
    translation = resp.content[0].text.strip()
    _translate_cache[cache_key] = translation
    return JSONResponse({"translation": translation})
