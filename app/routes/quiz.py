"""Quiz routes: fill-in-blank, MCQ, quiz sets, and completion."""

import re
import unicodedata

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from ..agent import run_agent_turn, track_quiz_grammar
from ..config import LEARNER_ID, PERSONA_REGISTRY
from ..database import append_chat_log
from ..state import ACTIVE_PERSONA, QUIZZES

router = APIRouter()


def _normalize(s: str) -> str:
    s = unicodedata.normalize("NFD", s.lower().strip())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s)


def _is_correct(user_answer: str, correct_answer: str) -> bool:
    return _normalize(user_answer) == _normalize(correct_answer)


@router.post("/quiz/answer", response_class=HTMLResponse)
def quiz_answer(
    request: Request,
    card_id: str = Form(...),
    blank_idx: int = Form(...),
    user_answer: str = Form(...),
):
    from ..main import templates

    quiz = QUIZZES.get(card_id)
    if quiz is None:
        return HTMLResponse("<div>(quiz expired)</div>")
    sentence = quiz["sentences"][blank_idx]
    correct = _is_correct(user_answer, sentence["answer"])
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


@router.post("/quiz/mcq", response_class=HTMLResponse)
def quiz_mcq(request: Request, card_id: str = Form(...), selected: int = Form(...)):
    from ..main import templates

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


@router.post("/quiz/set/answer", response_class=HTMLResponse)
def quiz_set_answer(
    request: Request, card_id: str = Form(...), selected: int = Form(...)
):
    from ..main import templates

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


@router.post("/quiz/set/next", response_class=HTMLResponse)
def quiz_set_next(request: Request, card_id: str = Form(...)):
    from ..main import templates

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
            {"card_id": card_id, "correct_count": correct_count, "total": total},
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


@router.post("/quiz/complete", response_class=HTMLResponse)
def quiz_complete(request: Request, card_id: str = Form(...)):
    from ..main import templates

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
        topic = quiz.get("topic", "")
        if topic:
            track_quiz_grammar(LEARNER_ID, topic, correct_count, total)
    elif quiz.get("type") == "mcq":
        r = quiz.get("result", {})
        summary = f"[MCQ result: {'correct' if r.get('correct') else 'wrong'}. React naturally, briefly.]"
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
    persona_info = PERSONA_REGISTRY.get(persona_id, PERSONA_REGISTRY["marta"])
    if result["text"]:
        append_chat_log(LEARNER_ID, persona_id, "persona", result["text"])
    return templates.TemplateResponse(
        request,
        "partials/persona_msg.html",
        {"persona_text": result["text"], "persona": persona_info},
    )
