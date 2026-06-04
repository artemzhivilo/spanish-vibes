# Spanish Vibes — `app/` (Phase 1 walking skeleton)

A FastAPI + HTMX app where one Claude agent (Marta, Sevilla teacher) chats in
Spanish, drops a single inline `fill_in_blank` exercise when it makes sense,
reacts to your answers, and saves learner notes to disk at session end.

This is the rebuild. The old `src/spanish_vibes/` tree is untouched.

## Run it

```bash
cd app
uv sync
export ANTHROPIC_API_KEY=sk-ant-...
uv run uvicorn main:app --reload
```

Then open http://127.0.0.1:8000.

(`uv` will create `.venv/` here from `pyproject.toml`. If you don't have `uv`
installed: `pip install uv`, or use stock `python -m venv .venv` +
`pip install -e .` with equivalent results.)

## Test loop

- Type a few messages to Marta. She should reply in mostly-Spanish, A2-ish.
- Talk about something concrete — a weekend, food, where you live.
- After a few exchanges she should drop one `fill_in_blank` card inline.
  Answer the blanks; she'll react to how you did.
- Say "bye" / "chau" / "me voy". She'll save notes to
  `memory/artem/learner.md` and send a farewell.
- Restart the server. Refresh the page. Send a new message — she should
  reference something from last session.

## Architecture

```
Browser (HTMX)
  │
  ├── POST /chat            → agent loop: chat OR card OR save_notes
  ├── POST /quiz/answer     → server-side string compare, no LLM
  └── POST /quiz/complete   → injects [exercise complete: …] into history,
                              calls agent for a reaction
main.py
  ├── anthropic client + 2 tool schemas
  ├── manual agent loop (claude-opus-4-7, adaptive thinking, prompt cache
  │   on the persona system prompt + injected memory)
  ├── HISTORY: dict[learner_id, messages]   (in-memory, single process)
  └── QUIZZES: dict[card_id, state]         (in-memory, server-evaluated)

personas/marta.md         Marta's voice + tool guidance + {learner_notes} slot
memory/{learner_id}/      learner.md — written by the agent via save_learner_notes
templates/                Jinja2 fragments returned from each route
static/style.css          Phase 1 styling — Phase 2 lands the visual design
```

## Deliberate non-features in Phase 1

- **Auth.** Single user. `LEARNER_ID = "artem"` is hardcoded in `main.py`.
  The memory layer is parameterized on `learner_id` from day one — going
  multi-user later is "add login + replace the constant with a session
  lookup."
- **Persistence beyond memory file.** Conversation history is in-process
  RAM. Server restart wipes it; that's fine — Marta reads the memory file
  and reconstructs context. (Phase 3 may persist history if turn-by-turn
  resume becomes useful.)
- **Other personas.** Diego, Rosa, Luis arrive in Phase 2.
- **Other tools.** Flashcards, grammar explainer, roleplay, word lookup
  arrive in Phase 2.
- **Voice.** Visual affordances ship in Phase 2 (mic on composer, speaker
  on bubbles), wired no-op. STT/TTS integration is Phase 4 or 5.
- **Visual design.** Phase 2 lands the high-fidelity design from the
  Claude Design handoff. This is intentionally minimal styling.
- **Tests.** Walking skeleton — manual test loop is the spec until Phase 1
  feels right.
