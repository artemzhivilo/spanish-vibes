"""FastAPI routes for the agent-based tutor system.

Route group: /tutor/
All UI interactions return HTMX partials that append to #tutor-chat.

Session state is held in a server-side dict (_SESSIONS) for Phase 1.
Each TutorSession lives for the browser tab's lifetime; it's re-created
on page load via POST /tutor/start.
"""

from __future__ import annotations

import json
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from .conversation import ConversationCard, ConversationEngine, ConversationMessage
from .db import get_current_user_id
from .personas import load_persona
from .tutor_agent import TutorActivityResult, TutorAction, TutorSession
from .tutor_db import (
    create_tutor_session as db_create_session,
    end_tutor_session as db_end_session,
    log_planner_decision,
    record_tutor_activity,
)
from .tutor_tools import (
    execute_tool,
    render_conversation_turn,
    render_drill_answer,
    render_translation_answer,
    render_circumlocution_result,
)

router = APIRouter(prefix="/tutor", tags=["tutor"])

_templates_path = (
    __import__("pathlib").Path(__file__).resolve().parent.parent.parent / "templates"
)
templates = Jinja2Templates(directory=str(_templates_path))

# In-memory session store — keyed by session_id string
_SESSIONS: dict[str, TutorSession] = {}

# ── Helpers ───────────────────────────────────────────────────────────────────


def _get_or_create_session(session_id: str, user_id: str) -> TutorSession:
    if session_id not in _SESSIONS:
        _SESSIONS[session_id] = TutorSession(session_id=session_id, user_id=user_id)
    return _SESSIONS[session_id]


def _html(content: str) -> HTMLResponse:
    return HTMLResponse(content=content)


def _plan_and_log(
    session: TutorSession,
    last_result: TutorActivityResult | None = None,
    context_hint: str | None = None,
) -> TutorAction:
    """Call planner and immediately log the decision to the database."""
    action = session.plan_next_action(last_result)
    try:
        log_planner_decision(
            session_id=session.session_id,
            tool_name=action.tool_name,
            tool_params=action.params,
            context_summary=context_hint or _activity_summary(session),
        )
    except Exception:
        pass  # logging never blocks the learner experience
    return action


def _activity_summary(session: TutorSession) -> str:
    """Short summary of session progress for the planner decision log."""
    n = len(session.activities)
    if n == 0:
        return "session start"
    last = session.activities[-1]
    return f"{n} activities done; last={last.activity_type} score={last.score:.0%}"


def _run_memory_tools(
    session: TutorSession,
    last_result: TutorActivityResult | None = None,
) -> TutorAction:
    """
    Ask the planner for the next action, silently executing any memory-tool
    calls before returning the first UI-producing action.

    The planner sometimes chains update_session_journal → update_grammar_notes
    before the next real activity.  This loop executes each write without
    sending any HTML to the browser, then asks the planner again.
    `last_result` is passed only on the first call; subsequent calls in the
    chain don't need it (planner already has it in context from the first call).
    """
    action = _plan_and_log(
        session, last_result=last_result, context_hint="post-activity"
    )
    while action.is_memory_tool:
        session.execute_memory_tool(action)
        action = _plan_and_log(session, context_hint="memory tool chain")
    return action


def _retry_html(session_id: str, message: str) -> str:
    """Fallback partial when the planner is unavailable."""
    return f"""\
<div class="tutor-message" id="msg-error">
  <div class="tutor-avatar">🧑‍🏫</div>
  <div class="tutor-bubble">
    <p class="tutor-text">{message}</p>
    <form hx-post="/tutor/respond"
          hx-target="#tutor-chat"
          hx-swap="beforeend"
          hx-on::after-request="scrollChat()"
          style="margin-top:0.5rem">
      <input type="hidden" name="session_id" value="{session_id}">
      <input type="hidden" name="message" value="retry">
      <input type="hidden" name="activity_type" value="retry">
      <button type="submit" class="chat-send-btn" style="width:100%">
        Try again →
      </button>
    </form>
  </div>
</div>"""


# ── Pages ─────────────────────────────────────────────────────────────────────


@router.get("", response_class=HTMLResponse)
async def get_tutor_page(request: Request) -> HTMLResponse:
    """Main tutor page. JS auto-POSTs to /tutor/start on DOMContentLoaded."""
    user_id = get_current_user_id() or "default"
    session_id = str(uuid.uuid4())
    return templates.TemplateResponse(
        "tutor.html",
        {"request": request, "session_id": session_id, "user_id": user_id},
    )


# ── Session start ─────────────────────────────────────────────────────────────


@router.post("/start", response_class=HTMLResponse)
def post_tutor_start(
    session_id: Annotated[str, Form()],
    user_id: Annotated[str, Form()],
) -> HTMLResponse:
    """
    Create TutorSession, read memory files, call planner (→ propose_session_plan).
    Also persists a DB row for the session.
    """
    session = _get_or_create_session(session_id, user_id)

    # Persist session to DB (fire-and-forget; never blocks the learner)
    try:
        db_create_session(session_id, user_id)
    except Exception:
        pass

    action = _plan_and_log(session, context_hint="session start")

    # Planner should always return propose_session_plan first; if it returned
    # a memory tool somehow, drain it then get a real action.
    while action.is_memory_tool:
        session.execute_memory_tool(action)
        action = _plan_and_log(session, context_hint="unexpected memory tool at start")

    result = execute_tool(action.tool_name, action.params, session)

    if not result.html:
        # Planner unavailable — show retry
        return _html(
            _retry_html(
                session_id, "I'm having a bit of trouble right now. Click to retry."
            )
        )

    return _html(result.html)


@router.post("/new-session", response_class=HTMLResponse)
def post_tutor_new_session(
    previous_session_id: Annotated[str, Form()] = "",
    user_id: Annotated[str, Form()] = "",
) -> HTMLResponse:
    """Start a fresh tutor session and return first planner-rendered activity."""
    if previous_session_id:
        _SESSIONS.pop(previous_session_id, None)

    resolved_user_id = user_id or (get_current_user_id() or "default")
    session_id = str(uuid.uuid4())
    session = _get_or_create_session(session_id, resolved_user_id)

    try:
        db_create_session(session_id, resolved_user_id)
    except Exception:
        pass

    action = _plan_and_log(session, context_hint="manual restart")
    while action.is_memory_tool:
        session.execute_memory_tool(action)
        action = _plan_and_log(
            session, context_hint="unexpected memory tool at restart"
        )

    result = execute_tool(action.tool_name, action.params, session)
    if action.tool_name == "end_session":
        _finalize_session(session, action)
        _drain_memory_tools_after_end(session)

    session_oob = (
        f'<input type="hidden" id="active-session-id" name="session_id" '
        f'value="{session_id}" hx-swap-oob="outerHTML">'
    )
    # Re-inject the thinking indicator since innerHTML wipes #tutor-chat
    thinking_html = (
        '<div id="tutor-thinking" class="tutor-message hidden">'
        '  <div class="tutor-avatar">🧑‍🏫</div>'
        '  <div class="tutor-bubble">'
        '    <span class="thinking-dot"></span>'
        '    <span class="thinking-dot"></span>'
        '    <span class="thinking-dot"></span>'
        "  </div>"
        "</div>"
    )
    if not result.html:
        return _html(
            session_oob
            + thinking_html
            + _retry_html(
                session_id, "I'm having a bit of trouble right now. Click to retry."
            )
        )

    return _html(session_oob + thinking_html + result.html)


# ── Learner chat response (between activities) ────────────────────────────────


@router.post("/respond", response_class=HTMLResponse)
def post_tutor_respond(
    session_id: Annotated[str, Form()],
    message: Annotated[str, Form()] = "",
    activity_type: Annotated[str, Form()] = "chat",
) -> HTMLResponse:
    """
    Learner sends a chat message between activities.
    Adds message to history → drains any memory tools → executes next activity.
    """
    session = _SESSIONS.get(session_id)
    if session is None:
        return _html(
            '<div class="tutor-message"><div class="tutor-bubble">'
            '<p class="tutor-text">Session expired. Please refresh the page.</p>'
            "</div></div>"
        )

    # ── Force end session when the End Session button is pressed ────────────
    if activity_type == "end_request":
        # Skip the planner entirely — force end_session immediately so the
        # learner doesn't wait for an LLM round-trip.
        # Build rich session-end data from actual session state.
        end_params = _build_end_session_params(session)
        action = TutorAction(
            tool_name="end_session",
            params=end_params,
            worker_briefing="",
            tutor_message="",
        )
        result = execute_tool(action.tool_name, action.params, session)
        _finalize_session(session, action)
        # Fire memory writes in background — don't block the response
        import threading

        threading.Thread(
            target=_drain_memory_tools_after_end,
            args=(session,),
            daemon=True,
        ).start()
        return _html(
            result.html or _retry_html(session_id, "Something went wrong. Try again?")
        )

    # Echo learner's message as a right-aligned bubble
    learner_bubble = f"""\
<div class="learner-message">
  <div class="learner-bubble">
    <p class="learner-text">{message}</p>
  </div>
</div>"""

    session.add_message("learner", message)

    # Get next planner action, draining any memory tools silently
    action = _plan_and_log(session, context_hint=f"learner replied: {message[:60]}")
    while action.is_memory_tool:
        session.execute_memory_tool(action)
        action = _plan_and_log(session, context_hint="memory tool after learner reply")

    result = execute_tool(action.tool_name, action.params, session)

    # Handle session end DB update + memory tool chain
    if action.tool_name == "end_session":
        _finalize_session(session, action)
        _drain_memory_tools_after_end(session)

    activity_html = result.html or _retry_html(
        session_id, "Something went wrong. Try again?"
    )
    # Remove the plan/free-chat input once a response is sent so a stale form
    # cannot fire duplicate /tutor/respond requests and start another activity.
    cleanup_oob = '<div id="plan-response-area" hx-swap-oob="delete"></div>'
    return _html(cleanup_oob + "\n" + learner_bubble + "\n" + activity_html)


# ── Conversation activity ─────────────────────────────────────────────────────


@router.post("/conversation/respond", response_class=HTMLResponse)
def post_conversation_respond(
    session_id: Annotated[str, Form()],
    user_message: Annotated[str, Form()],
    conv_state: Annotated[str, Form()],
    turns_done: Annotated[int, Form()],
    max_turns: Annotated[int, Form()],
) -> HTMLResponse:
    """Handle one conversation turn. Worker call only — no planner involved."""
    session = _SESSIONS.get(session_id)
    if session is None:
        return _html('<p class="text-red-400 text-sm">Session expired.</p>')

    try:
        state = json.loads(conv_state)
    except (json.JSONDecodeError, ValueError):
        return _html('<p class="text-red-400 text-sm">Invalid conversation state.</p>')

    topic = state.get("topic", "")
    concept = state.get("concept", "present")
    difficulty = int(state.get("difficulty", 2))
    persona_slug = state.get("persona_slug", "marta")
    persona_name = state.get("persona_name", "Marta")
    guardrails = state.get("guardrails", "")

    messages = [ConversationMessage.from_dict(m) for m in state.get("messages", [])]

    persona = load_persona(persona_slug)
    persona_prompt = persona.system_prompt if persona else None

    engine = ConversationEngine()
    result = engine.respond_to_user(
        messages=messages,
        user_text=user_message,
        topic=topic,
        concept=concept,
        difficulty=difficulty,
        persona_prompt=persona_prompt,
        persona_name=persona_name,
        conversation_guardrails=guardrails or None,
    )

    # Log the respond worker call for dev tools
    if (
        session
        and hasattr(engine, "_last_respond_prompt")
        and engine._last_respond_prompt
    ):
        session.log_worker_call(
            label="respond",
            model=engine._last_respond_model or "unknown",
            system_prompt=engine._last_respond_prompt or "",
            user_message=engine._last_respond_user or "",
            result=f"reply: {result.ai_reply}\ncorrections: {len(result.corrections)}",
        )

    # Append turn to in-state message history
    messages.append(
        ConversationMessage(
            role="user", content=user_message, corrections=result.corrections
        )
    )
    messages.append(ConversationMessage(role="ai", content=result.ai_reply))
    state["messages"] = [m.to_dict() for m in messages]
    new_conv_state = json.dumps(state)

    html = render_conversation_turn(
        user_message=user_message,
        ai_reply=result.ai_reply,
        corrections=result.corrections,
        persona_name=persona_name,
        turns_done=turns_done,
        max_turns=max_turns,
        session_id=session_id,
        conv_state_json=new_conv_state,
    )
    return _html(html)


@router.post("/conversation/complete", response_class=HTMLResponse)
def post_conversation_complete(
    session_id: Annotated[str, Form()],
    conv_state: Annotated[str, Form()],
) -> HTMLResponse:
    """
    Conversation finished. Evaluate, record in DB + session, ask planner what's next.
    """
    session = _SESSIONS.get(session_id)
    if session is None:
        return _html('<p class="text-red-400 text-sm">Session expired.</p>')

    try:
        state = json.loads(conv_state)
    except (json.JSONDecodeError, ValueError):
        return _html('<p class="text-red-400 text-sm">Invalid conversation state.</p>')

    messages = [ConversationMessage.from_dict(m) for m in state.get("messages", [])]
    topic = state.get("topic", "")
    concept = state.get("concept", "")
    persona_slug = state.get("persona_slug", "marta")
    persona_name = state.get("persona_name", "Marta")

    conv = ConversationCard(
        topic=topic,
        concept=concept,
        difficulty=int(state.get("difficulty", 2)),
        opener=messages[0].content if messages else "",
        max_turns=int(state.get("max_turns", 4)),
        messages=messages,
        persona_name=persona_name,
    )

    persona = load_persona(persona_slug)
    persona_prompt = persona.system_prompt if persona else None
    engine = ConversationEngine()
    summary = engine.generate_summary(
        conv, persona_prompt=persona_prompt, persona_name=persona_name
    )

    errors = [
        f"{c.concept_id}: said '{c.original}' → {c.corrected}"
        for c in summary.corrections[:8]
    ]
    notes = (
        f"Score {summary.score:.0%}. {len(summary.corrections)} corrections. "
        f"Turns: {conv.user_turn_count}/{conv.max_turns}. "
        f"Concepts: {', '.join(summary.concepts_practiced[:3])}."
    )
    last_result = TutorActivityResult(
        activity_type="conversation",
        score=summary.score,
        errors=errors,
        concepts_practiced=summary.concepts_practiced,
        notes=notes,
    )
    session.record_activity(last_result)

    # Persist to DB
    try:
        record_tutor_activity(
            session_id=session_id,
            activity_type="conversation",
            tool_params={"topic": topic, "concept": concept, "persona": persona_slug},
            result={"score": summary.score, "errors": errors, "notes": notes},
            score=summary.score,
            concept_id=concept or None,
        )
    except Exception:
        pass

    # Planner decides what's next (drain memory tools first)
    action = _run_memory_tools(session, last_result=last_result)
    result = execute_tool(action.tool_name, action.params, session)

    if action.tool_name == "end_session":
        _finalize_session(session, action)
        _drain_memory_tools_after_end(session)

    return _html(
        result.html or _retry_html(session_id, "Something went wrong. Try again?")
    )


# ── Conjugation drill ─────────────────────────────────────────────────────────


@router.post("/drill/answer", response_class=HTMLResponse)
def post_drill_answer(
    session_id: Annotated[str, Form()],
    items_json: Annotated[str, Form()],
    current_index: Annotated[int, Form()],
    correct_count: Annotated[int, Form()],
    errors_json: Annotated[str, Form()],
    user_answer: Annotated[str, Form()],
    item_started_at: Annotated[int, Form()] = 0,
    response_times_json: Annotated[str, Form()] = "[]",
) -> HTMLResponse:
    """Process one drill answer. Stateless — all state is in hidden form fields."""
    try:
        items: list[dict] = json.loads(items_json)
        errors: list[str] = json.loads(errors_json)
    except (json.JSONDecodeError, ValueError):
        return _html('<p class="text-red-400 text-sm">Invalid drill state.</p>')

    html, _complete = render_drill_answer(
        items=items,
        current_index=current_index,
        correct_count=correct_count,
        errors=errors,
        user_answer=user_answer,
        session_id=session_id,
        item_started_at=item_started_at,
        response_times_json=response_times_json,
    )
    return _html(html)


@router.post("/drill/complete", response_class=HTMLResponse)
def post_drill_complete(
    session_id: Annotated[str, Form()],
    score: Annotated[float, Form()],
    errors_json: Annotated[str, Form()],
    total: Annotated[int, Form()],
) -> HTMLResponse:
    """Drill finished. Record result in DB + session, ask planner what's next."""
    session = _SESSIONS.get(session_id)
    if session is None:
        return _html('<p class="text-red-400 text-sm">Session expired.</p>')

    try:
        errors: list[str] = json.loads(errors_json)
    except (json.JSONDecodeError, ValueError):
        errors = []

    correct = int(round(score * total))
    last_result = TutorActivityResult(
        activity_type="conjugation_drill",
        score=score,
        errors=errors[:8],
        concepts_practiced=["verb_conjugation"],
        notes=f"Score {score:.0%}. {correct}/{total} correct.",
    )
    session.record_activity(last_result)

    # Persist to DB
    try:
        record_tutor_activity(
            session_id=session_id,
            activity_type="conjugation_drill",
            result={
                "score": score,
                "correct": correct,
                "total": total,
                "errors": errors[:8],
            },
            score=score,
            concept_id="verb_conjugation",
        )
    except Exception:
        pass

    # Planner decides what's next (drain memory tools first)
    action = _run_memory_tools(session, last_result=last_result)
    result = execute_tool(action.tool_name, action.params, session)

    if action.tool_name == "end_session":
        _finalize_session(session, action)
        _drain_memory_tools_after_end(session)

    return _html(
        result.html or _retry_html(session_id, "Something went wrong. Try again?")
    )


# ── Translation challenge ─────────────────────────────────────────────────────


@router.post("/translation/answer", response_class=HTMLResponse)
def post_translation_answer(
    session_id: Annotated[str, Form()],
    sentences_json: Annotated[str, Form()],
    current_index: Annotated[int, Form()],
    correct_count: Annotated[int, Form()],
    scores_json: Annotated[str, Form()],
    corrections_json: Annotated[str, Form()],
    user_translation: Annotated[str, Form()],
    target_grammar: Annotated[str, Form()] = "",
    difficulty: Annotated[int, Form()] = 2,
    hints_json: Annotated[str, Form()] = "[]",
    worker_briefing: Annotated[str, Form()] = "",
) -> HTMLResponse:
    """Evaluate one translation. Stateless — all state in hidden form fields."""
    try:
        sentences: list[str] = json.loads(sentences_json)
        scores: list[float] = json.loads(scores_json)
        all_corrections: list[list[dict]] = json.loads(corrections_json)
        hints: list[str] = json.loads(hints_json)
    except (json.JSONDecodeError, ValueError):
        return _html('<p class="text-red-400 text-sm">Invalid translation state.</p>')

    html, _complete = render_translation_answer(
        sentences=sentences,
        current_index=current_index,
        correct_count=correct_count,
        scores=scores,
        all_corrections=all_corrections,
        user_translation=user_translation,
        session_id=session_id,
        target_grammar=target_grammar,
        difficulty=difficulty,
        hints=hints,
        worker_briefing=worker_briefing,
    )
    return _html(html)


@router.post("/translation/complete", response_class=HTMLResponse)
def post_translation_complete(
    session_id: Annotated[str, Form()],
    score: Annotated[float, Form()],
    errors_json: Annotated[str, Form()],
    total: Annotated[int, Form()],
) -> HTMLResponse:
    """All sentences done. Record result in DB + session, ask planner what's next."""
    session = _SESSIONS.get(session_id)
    if session is None:
        return _html('<p class="text-red-400 text-sm">Session expired.</p>')

    try:
        errors: list[str] = json.loads(errors_json)
    except (json.JSONDecodeError, ValueError):
        errors = []

    correct = int(round(score * total))
    last_result = TutorActivityResult(
        activity_type="translation_challenge",
        score=score,
        errors=errors[:8],
        concepts_practiced=["translation"],
        notes=f"Score {score:.0%}. {correct}/{total} communicated successfully.",
    )
    session.record_activity(last_result)

    try:
        record_tutor_activity(
            session_id=session_id,
            activity_type="translation_challenge",
            result={
                "score": score,
                "correct": correct,
                "total": total,
                "errors": errors[:8],
            },
            score=score,
            concept_id="translation",
        )
    except Exception:
        pass

    action = _run_memory_tools(session, last_result=last_result)
    result = execute_tool(action.tool_name, action.params, session)

    if action.tool_name == "end_session":
        _finalize_session(session, action)
        _drain_memory_tools_after_end(session)

    return _html(
        result.html or _retry_html(session_id, "Something went wrong. Try again?")
    )


# ── Circumlocution challenge ──────────────────────────────────────────────────


@router.post("/circumlocution/submit", response_class=HTMLResponse)
def post_circumlocution_submit(
    session_id: Annotated[str, Form()],
    prompt_en: Annotated[str, Form()],
    learner_response: Annotated[str, Form()],
    target_grammar: Annotated[str, Form()] = "",
    vocabulary_level: Annotated[str, Form()] = "A2",
    hints_json: Annotated[str, Form()] = "[]",
    worker_briefing: Annotated[str, Form()] = "",
) -> HTMLResponse:
    """Evaluate circumlocution response. Swaps the activity card with results."""
    try:
        hints: list[str] = json.loads(hints_json)
    except (json.JSONDecodeError, ValueError):
        hints = []

    html, _score = render_circumlocution_result(
        prompt_en=prompt_en,
        learner_response=learner_response,
        session_id=session_id,
        target_grammar=target_grammar,
        vocabulary_level=vocabulary_level,
        hints=hints,
        worker_briefing=worker_briefing,
    )
    return _html(html)


@router.post("/circumlocution/complete", response_class=HTMLResponse)
def post_circumlocution_complete(
    session_id: Annotated[str, Form()],
    score: Annotated[float, Form()],
    comm_score: Annotated[float, Form()] = 0.7,
    gram_score: Annotated[float, Form()] = 0.7,
    res_score: Annotated[float, Form()] = 0.7,
    errors_json: Annotated[str, Form()] = "[]",
) -> HTMLResponse:
    """Record circumlocution result in DB + session, ask planner what's next."""
    session = _SESSIONS.get(session_id)
    if session is None:
        return _html('<p class="text-red-400 text-sm">Session expired.</p>')

    try:
        errors: list[str] = json.loads(errors_json)
    except (json.JSONDecodeError, ValueError):
        errors = []

    last_result = TutorActivityResult(
        activity_type="circumlocution_challenge",
        score=score,
        errors=errors[:8],
        concepts_practiced=["circumlocution", "communication_strategy"],
        notes=(
            f"Score {score:.0%}. "
            f"Communication {comm_score:.0%}, Grammar {gram_score:.0%}, "
            f"Resourcefulness {res_score:.0%}."
        ),
    )
    session.record_activity(last_result)

    try:
        record_tutor_activity(
            session_id=session_id,
            activity_type="circumlocution_challenge",
            result={
                "score": score,
                "communication_score": comm_score,
                "grammar_score": gram_score,
                "resourcefulness_score": res_score,
                "errors": errors[:8],
            },
            score=score,
            concept_id="circumlocution",
        )
    except Exception:
        pass

    action = _run_memory_tools(session, last_result=last_result)
    result = execute_tool(action.tool_name, action.params, session)

    if action.tool_name == "end_session":
        _finalize_session(session, action)
        _drain_memory_tools_after_end(session)

    return _html(
        result.html or _retry_html(session_id, "Something went wrong. Try again?")
    )


# ── Internal helpers ──────────────────────────────────────────────────────────


def _build_end_session_params(session: TutorSession) -> dict[str, Any]:
    """Build rich end_session params from actual session state.

    Called when the learner clicks "End Session" to generate meaningful
    feedback without an LLM round-trip.
    """
    acts = session.activities
    total = len(acts)

    # ── Activities summary (the tool has fallback logic too, but be explicit) ─
    activities_summary = []
    for a in acts:
        activities_summary.append(
            {
                "type": a.activity_type,
                "score": max(0.0, min(1.0, float(a.score))),
                "highlight": a.notes,
            }
        )

    # ── Breakthroughs: high-scoring activities or concepts ────────────────────
    breakthroughs: list[str] = []
    for a in acts:
        if a.score >= 0.8:
            concepts_str = (
                ", ".join(a.concepts_practiced[:2]) if a.concepts_practiced else ""
            )
            label = a.activity_type.replace("_", " ")
            if concepts_str:
                breakthroughs.append(
                    f"Scored {a.score:.0%} on {label} ({concepts_str})"
                )
            else:
                breakthroughs.append(f"Scored {a.score:.0%} on {label}")
    if not breakthroughs and acts:
        # If no high scores, celebrate effort
        breakthroughs.append(
            f"Completed {total} {'activity' if total == 1 else 'activities'} this session"
        )

    # ── Still working on: low-scoring activities or things with errors ────────
    still_working_on: list[str] = []
    all_concepts: set[str] = set()
    for a in acts:
        all_concepts.update(a.concepts_practiced)
        if a.score < 0.7 and a.errors:
            # Pick the first 1-2 errors as examples
            for err in a.errors[:2]:
                still_working_on.append(err)
        elif a.score < 0.7:
            label = a.activity_type.replace("_", " ")
            concepts_str = (
                ", ".join(a.concepts_practiced[:2]) if a.concepts_practiced else ""
            )
            if concepts_str:
                still_working_on.append(f"{label}: {concepts_str} needs more practice")
            else:
                still_working_on.append(f"{label} needs more practice")
    # Deduplicate and limit
    still_working_on = list(dict.fromkeys(still_working_on))[:4]

    # ── Summary message ──────────────────────────────────────────────────────
    if total == 0:
        summary_message = "Session ended. See you next time!"
    else:
        avg_score = sum(a.score for a in acts) / total
        if avg_score >= 0.8:
            summary_message = (
                f"Great session! You completed {total} "
                f"{'activity' if total == 1 else 'activities'} "
                f"with an average score of {avg_score:.0%}. ¡Excelente!"
            )
        elif avg_score >= 0.6:
            summary_message = (
                f"Good work! You tackled {total} "
                f"{'activity' if total == 1 else 'activities'} "
                f"with an average score of {avg_score:.0%}. Keep it up!"
            )
        else:
            summary_message = (
                f"You put in the effort with {total} "
                f"{'activity' if total == 1 else 'activities'}. "
                f"Every session makes you stronger — ¡vamos!"
            )

    # ── Next session preview ─────────────────────────────────────────────────
    if still_working_on:
        next_session_preview = "We'll focus on the areas that need more practice."
    elif all_concepts:
        next_session_preview = (
            f"We'll build on today's work with {', '.join(list(all_concepts)[:2])}."
        )
    else:
        next_session_preview = "We'll pick up where you left off."

    return {
        "summary_message": summary_message,
        "activities_summary": activities_summary,
        "breakthroughs": breakthroughs,
        "still_working_on": still_working_on,
        "next_session_preview": next_session_preview,
        "session_number": session.session_number,
    }


def _finalize_session(session: TutorSession, action: TutorAction) -> None:
    """Write session-end data to the DB when the planner calls end_session."""
    try:
        summary = action.params.get("summary_message", "")
        db_end_session(session.session_id, session_summary=summary)
    except Exception:
        pass


def _drain_memory_tools_after_end(session: TutorSession) -> None:
    """
    After end_session, explicitly ask the planner to write session journal
    and grammar notes.

    Runs up to 4 additional planner calls with explicit instructions to
    call update_session_journal then update_grammar_notes.
    Stops as soon as no more memory tools are returned.
    """
    from datetime import datetime, timezone

    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Build a summary of this session for the journal-write context
    acts = session.activities
    act_summary = (
        "; ".join(f"{a.activity_type} {a.score:.0%}" for a in acts)
        if acts
        else "no activities"
    )
    errors = [e for a in acts for e in a.errors[:3]][:6]
    error_str = "; ".join(errors) if errors else "none recorded"

    journal_ctx = (
        f"Session just ended ({date_str}). Activities: {act_summary}. "
        f"Key errors: {error_str}. "
        "Now call update_session_journal to record this session. "
        "Do NOT call end_session again."
    )

    grammar_ctx = (
        f"Session journal written. Now call update_grammar_notes "
        f"to update grammar tracking based on: {act_summary}. Errors: {error_str}. "
        "Do NOT call end_session or update_session_journal again."
    )

    contexts = [journal_ctx, grammar_ctx, grammar_ctx, grammar_ctx]

    for ctx in contexts:
        try:
            action = _plan_and_log_with_context(session, ctx)
            if not action.is_memory_tool:
                break  # planner returned something else — stop
            session.execute_memory_tool(action)
        except Exception:
            break


def _plan_and_log_with_context(
    session: TutorSession, context_override: str
) -> "TutorAction":
    """Call planner with explicit context override and log the decision."""
    action = session.plan_next_action(context_override=context_override)
    try:
        log_planner_decision(
            session_id=session.session_id,
            tool_name=action.tool_name,
            tool_params=action.params,
            context_summary=context_override[:120],
        )
    except Exception:
        pass
    return action


# ── Dev tools ────────────────────────────────────────────────────────────────


@router.get("/dev/prompts", response_class=HTMLResponse)
async def get_dev_prompts(session_id: str = "") -> HTMLResponse:
    """Return the debug prompt log for a session as an HTML partial."""
    session = _SESSIONS.get(session_id)
    if session is None:
        return _html('<p class="text-slate-500 text-sm">No active session found.</p>')

    if not session.debug_log:
        return _html('<p class="text-slate-500 text-sm">No prompts captured yet.</p>')

    import html as html_mod

    entries_html: list[str] = []
    for i, entry in enumerate(session.debug_log):
        ts = entry.timestamp[11:19] if len(entry.timestamp) > 19 else entry.timestamp
        label_colors = {
            "planner": "bg-violet-900 text-violet-300",
            "opener": "bg-blue-900 text-blue-300",
            "respond": "bg-emerald-900 text-emerald-300",
            "translation_eval": "bg-amber-900 text-amber-300",
        }
        badge_cls = label_colors.get(entry.label, "bg-slate-700 text-slate-300")
        sys_esc = html_mod.escape(entry.system_prompt)
        usr_esc = html_mod.escape(entry.user_message)
        res_esc = html_mod.escape(entry.tool_result)
        entries_html.append(f"""\
<details class="dev-prompt-entry" {"open" if i == len(session.debug_log) - 1 else ""}>
  <summary class="dev-prompt-summary">
    <span class="dev-prompt-badge {badge_cls}">{html_mod.escape(entry.label)}</span>
    <span class="dev-prompt-model">{html_mod.escape(entry.model)}</span>
    <span class="dev-prompt-time">{ts}</span>
  </summary>
  <div class="dev-prompt-body">
    <div class="dev-prompt-section">
      <span class="dev-prompt-label">System Prompt</span>
      <pre class="dev-prompt-pre">{sys_esc}</pre>
    </div>
    <div class="dev-prompt-section">
      <span class="dev-prompt-label">User Message</span>
      <pre class="dev-prompt-pre">{usr_esc}</pre>
    </div>
    <div class="dev-prompt-section">
      <span class="dev-prompt-label">Result</span>
      <pre class="dev-prompt-pre dev-prompt-result">{res_esc}</pre>
    </div>
  </div>
</details>""")

    return _html("\n".join(entries_html))
