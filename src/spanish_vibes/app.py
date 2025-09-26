from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.responses import Response

from .srs import (
    Card,
    count_due,
    fetch_card,
    init_db,
    insert_card,
    next_due_card,
    recent_cards,
    schedule,
)

PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_ROOT.parent.parent
TEMPLATES_DIR = PROJECT_ROOT / "templates"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Ensure the database schema exists even when lifespan hooks are not triggered (e.g. in tests).
init_db()


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="Spanish Vibes", lifespan=lifespan)


def _is_hx(request: Request) -> bool:
    return request.headers.get("HX-Request", "false").lower() == "true"


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> Response:
    now = datetime.now(timezone.utc)
    cards = recent_cards(limit=10)
    context = {
        "page_title": "Spanish Vibes",
        "due_count": count_due(now),
        "cards": cards,
    }
    return templates.TemplateResponse(request, "index.html", context)


@app.post("/add", response_class=HTMLResponse)
async def add_card(
    request: Request,
    front: str = Form(...),
    back: str = Form(...),
    example: str = Form("")
) -> Response:
    now = datetime.now(timezone.utc)
    try:
        card = insert_card(front, back, example or None, now=now)
    except ValueError:
        return HTMLResponse("Front and back are required.", status_code=status.HTTP_400_BAD_REQUEST)

    if _is_hx(request):
        return templates.TemplateResponse(request, "partials/card_row.html", {"card": card})

    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/quiz", response_class=HTMLResponse)
async def quiz_panel(request: Request) -> Response:
    now = datetime.now(timezone.utc)
    card = next_due_card(now)
    return templates.TemplateResponse(request, "quiz.html", {"card": card, "revealed": False})


@app.get("/reveal/{card_id}", response_class=HTMLResponse)
async def reveal_card(request: Request, card_id: int) -> Response:
    card = fetch_card(card_id)
    if card is None:
        return templates.TemplateResponse(request, "quiz.html", {"card": None, "revealed": False})
    return templates.TemplateResponse(request, "quiz.html", {"card": card, "revealed": True})


@app.post("/grade/{card_id}/{verdict}", response_class=HTMLResponse)
async def grade_card(
    request: Request,
    card_id: int,
    verdict: Literal["good", "again"],
) -> Response:
    card: Card | None = fetch_card(card_id)
    now = datetime.now(timezone.utc)
    if card is not None:
        schedule(card, verdict, now)
    next_card = next_due_card(now)
    return templates.TemplateResponse(request, "quiz.html", {"card": next_card, "revealed": False})


def main() -> None:
    import uvicorn

    uvicorn.run("spanish_vibes.app:app", host="127.0.0.1", port=8000, reload=True)


if __name__ == "__main__":
    main()
