"""Spanish Vibes — FastAPI app entrypoint.

A chat-first Spanish learning app where Claude acts as tutor personas.
This module sets up the FastAPI app, mounts static files, includes route
modules, and serves the main page.
"""

from __future__ import annotations


from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from jinja2 import Environment, FileSystemLoader, select_autoescape

from .config import APP_DIR, LEARNER_ID, MODEL, PERSONA_REGISTRY
from .database import get_chat_log, get_or_create_learner, init_db
from .state import ACTIVE_PERSONA

# Load .env (local dev only — production uses real env vars)
load_dotenv(APP_DIR / ".env", override=True)

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(title="Spanish Vibes", version="0.2.0")

# Initialize the database
init_db()
get_or_create_learner(LEARNER_ID)

# Static files
app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")

# Templates (cache_size=0 sidesteps a Jinja2 3.1.6 LRU bug on Python 3.14)
_jinja_env = Environment(
    loader=FileSystemLoader(APP_DIR / "templates"),
    autoescape=select_autoescape(["html"]),
    cache_size=0,
)
templates = Jinja2Templates(env=_jinja_env)

# ---------------------------------------------------------------------------
# Include route modules
# ---------------------------------------------------------------------------

from .routes.chat import router as chat_router  # noqa: E402
from .routes.learner import router as learner_router  # noqa: E402
from .routes.persona import router as persona_router  # noqa: E402
from .routes.placement import router as placement_router  # noqa: E402
from .routes.quiz import router as quiz_router  # noqa: E402

app.include_router(chat_router)
app.include_router(quiz_router)
app.include_router(placement_router)
app.include_router(persona_router)
app.include_router(learner_router)

# ---------------------------------------------------------------------------
# Main page
# ---------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    persona_id = ACTIVE_PERSONA.get(LEARNER_ID, "marta")
    persona_info = PERSONA_REGISTRY.get(persona_id, PERSONA_REGISTRY["marta"])
    chat_log = get_chat_log(LEARNER_ID, persona_id)
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "persona_id": persona_id,
            "persona": persona_info,
            "all_personas": PERSONA_REGISTRY,
            "chat_log": chat_log,
        },
    )


@app.get("/healthz")
def healthz():
    return {"ok": True, "model": MODEL, "learner_id": LEARNER_ID}
