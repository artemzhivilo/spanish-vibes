# Repository Guidelines

## Project Structure & Module Organization
Core Python code lives in `src/spanish_vibes`, separated by domain: FastAPI setup in `app.py`, spaced-repetition logic in `srs.py`, flow orchestration in the `flow_*.py` modules, and persistence helpers in `db.py`/`flow_db.py`. User-facing copy and markdown lessons live in `content/`, while `templates/` hosts the HTMX + Jinja files referenced by `web.py`. Local data such as `data/concepts.yaml` and the SQLite file `data/spanish_vibes.db` seed the experience. Reference material lives in `docs/` and `book/`. Tests mirror the module layout inside `tests/test_*.py`.

## Build, Test, and Development Commands
Install dependencies with `uv sync` (reads both `pyproject.toml` and `uv.lock`). Start the server using `uv run uvicorn spanish_vibes.app:app --reload --app-dir src` for automatic reloads and HTMX templates. Run linting and formatting with `uv run ruff check` and `uv run ruff format`. Validate behavior through `uv run pytest`, and use `uv run pytest tests/test_flow_routes.py -k quiz` for targeted suites. Build distributable wheels via `uv build` before publishing.

## Coding Style & Naming Conventions
Target Python 3.11+, four-space indents, and exhaustive type hints (dataclasses + Literals are already prevalent). Keep module-level constants SCREAMING_SNAKE_CASE, route handlers as verbs (`get_dashboard`, `post_feedback`), and database helpers as noun-based functions (`fetch_lesson_by_slug`). Template context keys and JSON payload fields should stay lowercase_with_underscores. Ruff enforces imports, unused code, and formatting—do not bypass it.

## Testing Guidelines
Pytest drives coverage; every new module should ship with a matching `tests/test_<module>.py`. Prefer pure unit tests around scheduling math in `srs.py` and flow-state reducers, then integration tests that hit the in-process FastAPI app. Mock external services by patching `flow_ai.ai_available`/`_get_client` so CI never contacts OpenAI. Maintain deterministic fixtures by copying or regenerating `data/spanish_vibes.db` rather than editing it in-place mid-test.

## Commit & Pull Request Guidelines
Follow the existing history: concise, imperative subjects (`Add Flow Mode v2...`) under ~72 characters, optionally prefixed with a scope (`flow:`) when it clarifies impact. Each PR should explain the motivation, summarize behavioral changes, list test commands that passed, and include screenshots or cURL snippets for UI/API tweaks. Call out migrations to `data/concepts.yaml` or `templates/` so reviewers know to reseed local assets.

## Security & Configuration Tips
Do not commit secrets. Set `OPENAI_API_KEY` in your shell (or a local `.env` ignored by git) to enable AI MCQ generation; without it the offline fallback remains active. Treat `data/spanish_vibes.db` as disposable—delete it to reseed via `init_db()` when schema drifts. Avoid logging raw prompts, completions, or user submissions to keep learner data private.
