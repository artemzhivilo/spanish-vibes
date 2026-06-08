"""Persona routes: switching and current persona info."""

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse

from ..config import LEARNER_ID, PERSONA_REGISTRY
from ..state import ACTIVE_PERSONA

router = APIRouter()


@router.post("/persona/switch", response_class=HTMLResponse)
def switch_persona(request: Request, persona_id: str = Form(...)):
    """Switch the active persona. Returns HX-Redirect to reload the page."""
    if persona_id not in PERSONA_REGISTRY:
        return HTMLResponse("Unknown persona", status_code=400)
    ACTIVE_PERSONA[LEARNER_ID] = persona_id
    return HTMLResponse("", headers={"HX-Redirect": "/"})


@router.get("/persona/current")
def current_persona():
    """Return the current persona info as JSON."""
    persona_id = ACTIVE_PERSONA.get(LEARNER_ID, "marta")
    info = PERSONA_REGISTRY.get(persona_id, PERSONA_REGISTRY["marta"])
    return JSONResponse({"id": persona_id, **info})
