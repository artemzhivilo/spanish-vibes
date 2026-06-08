"""Chat route: /chat endpoint."""

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from ..agent import run_agent_turn
from ..config import LEARNER_ID, PERSONA_REGISTRY
from ..database import append_chat_log
from ..state import ACTIVE_PERSONA

router = APIRouter()


@router.post("/chat", response_class=HTMLResponse)
def chat(request: Request, message: str = Form(...)):
    """Send a user message, get back HTML fragments to append to #chat."""
    from ..main import templates

    text = message.strip()
    if not text:
        return HTMLResponse("")
    persona_id = ACTIVE_PERSONA.get(LEARNER_ID, "marta")
    result = run_agent_turn(LEARNER_ID, text, persona_id)
    persona_info = PERSONA_REGISTRY.get(persona_id, PERSONA_REGISTRY["marta"])
    # Persist to DB chat log
    append_chat_log(LEARNER_ID, persona_id, "user", text)
    if result["text"]:
        append_chat_log(LEARNER_ID, persona_id, "persona", result["text"])
    return templates.TemplateResponse(
        request,
        "partials/turn.html",
        {
            "user_text": text,
            "persona_text": result["text"],
            "cards": result["cards"],
            "persona_id": persona_id,
            "persona": persona_info,
        },
    )
