"""Placement test routes."""

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from ..agent import (
    compute_placement_result,
    pick_placement_question,
    run_agent_turn,
)
from ..config import LEARNER_ID, PERSONA_REGISTRY
from ..database import append_chat_log, update_grammar_status, update_learner_profile
from ..placement_questions import PlacementQuestion
from ..state import ACTIVE_PERSONA, QUIZZES

router = APIRouter()


@router.post("/placement/answer", response_class=HTMLResponse)
def placement_answer(
    request: Request, card_id: str = Form(...), selected: int = Form(...)
):
    from ..main import templates

    quiz = QUIZZES.get(card_id)
    if quiz is None:
        return HTMLResponse("<div>(quiz expired)</div>")

    q: PlacementQuestion = quiz["current_question"]
    correct = selected == q.correct_index

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


@router.post("/placement/next", response_class=HTMLResponse)
def placement_next(request: Request, card_id: str = Form(...)):
    from ..main import templates

    quiz = QUIZZES.get(card_id)
    if quiz is None:
        return HTMLResponse("<div>(quiz expired)</div>")

    idx = quiz["current_index"]
    if idx >= quiz["total"]:
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

    asked = set(quiz["asked_indices"])
    pick = pick_placement_question(quiz["difficulty"], asked)
    if pick is None:
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


@router.post("/placement/complete", response_class=HTMLResponse)
def placement_complete(request: Request, card_id: str = Form(...)):
    from ..main import templates

    quiz = QUIZZES.pop(card_id, None)
    if quiz is None:
        return HTMLResponse("")

    result = compute_placement_result(quiz)
    update_learner_profile(LEARNER_ID, cefr_level=result["level"])
    for gap in result.get("gaps", []):
        update_grammar_status(LEARNER_ID, gap, "gap")

    summary = result["summary_text"]
    persona_id = ACTIVE_PERSONA.get(LEARNER_ID, "marta")
    agent_result = run_agent_turn(LEARNER_ID, summary, persona_id)
    persona_info = PERSONA_REGISTRY.get(persona_id, PERSONA_REGISTRY["marta"])
    if agent_result["text"]:
        append_chat_log(LEARNER_ID, persona_id, "persona", agent_result["text"])
    return templates.TemplateResponse(
        request,
        "partials/persona_msg.html",
        {"persona_text": agent_result["text"], "persona": persona_info},
    )
