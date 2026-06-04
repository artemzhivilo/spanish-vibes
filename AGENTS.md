# AGENTS.md

## Project Overview

Spanish Vibes is a FastAPI + HTMX Spanish learning app. It combines spaced
repetition, adaptive flow cards, AI conversation practice, learner memory, and
Spanish lesson content.

The main application lives at the repository root:

- `src/spanish_vibes/` - Python package for the production-style app
- `templates/` - Jinja/HTMX templates for the root app
- `content/` - markdown lesson content
- `data/` - seed data, concept maps, prompts, dictionaries, and local runtime data
- `tests/` - pytest coverage for the root app
- `docs/` - architecture notes, implementation prompts, and design references

There is also an `app/` directory used as a separate walking-skeleton rebuild.
Treat it as a separate app surface with its own `pyproject.toml`, lockfile, and
run command. Do not mix code between `src/spanish_vibes/` and `app/` unless the
task explicitly asks for a migration or integration.

## Setup

Root app:

```bash
uv sync
uv run spanish-vibes
```

Then open <http://localhost:8000>.

Alternative development server:

```bash
uv run uvicorn spanish_vibes.app:app --reload --app-dir src --port 8080
```

Walking-skeleton app, only when the task targets `app/`:

```bash
cd app
uv sync
uv run uvicorn main:app --reload
```

## Configuration

Set secrets in the shell or a local `.env` file. Never commit them.

- `OPENAI_API_KEY` enables root-app AI generation. Without it, offline fallbacks
  should keep tests and basic flows deterministic.
- `ANTHROPIC_API_KEY` is used by the Claude/Marta walking-skeleton flow and any
  Anthropic-backed tutor experiments.
- Local SQLite state lives under `data/`. Treat learner/session data as private
  runtime data unless a task explicitly says to commit a fixture.

## Architecture

Main app flow:

```text
FastAPI routes -> flow/tutor/conversation modules -> SQLite helpers -> HTMX templates
```

Important modules:

- `src/spanish_vibes/app.py` - FastAPI app setup, auth middleware, root routes
- `src/spanish_vibes/flow_routes.py` - adaptive Flow Mode route handlers
- `src/spanish_vibes/flow_ai.py` - AI card/conversation generation and fallbacks
- `src/spanish_vibes/conversation.py` - conversation engine and persona behavior
- `src/spanish_vibes/tutor_*.py` - newer tutor agent, memory, tools, and routes
- `src/spanish_vibes/db.py` and `src/spanish_vibes/flow_db.py` - SQLite schema
  and persistence helpers
- `src/spanish_vibes/bkt.py`, `srs.py`, `evaluation.py`, `interest.py` -
  learning-model and analytics logic
- `src/spanish_vibes/template_helpers.py` - shared Jinja filters/helpers

Content and prompt assets:

- `content/lessons/` - lesson markdown
- `data/concepts.yaml` - concept graph
- `data/prompts.yaml` - prompt configuration
- `data/personas/` - persona data
- `docs/prompts/` - agent prompt handoffs and implementation prompts

## Development Workflow

1. Branch off `master`; do not work directly on `master`.

   ```bash
   git checkout master
   git pull
   git checkout -b codex/short-description
   ```

2. Keep PRs small. Aim for fewer than 200 meaningful changed lines unless the
   change is mostly generated content or fixtures.

3. Before editing, check the working tree:

   ```bash
   git status --short --branch
   ```

   If unrelated user changes are present, leave them alone. If they affect the
   task, work with them rather than reverting them.

4. Make the smallest change that satisfies the request and follows existing
   local patterns.

5. Run the verification loop before handoff:

   ```bash
   uv run ruff check .
   uv run ruff format --check .
   uv run pytest
   ```

6. Open a PR with motivation, behavior changes, test commands, and screenshots
   or short cURL examples for UI/API changes.

7. Run `/code-review` in Codex on the PR diff before merging. Use
   `/code-review low` for docs, prompts, and tooling-only changes.

## Tools

- `uv` - Python package/dependency manager. Prefer `uv run ...` for commands.
- `ruff` - linting and formatting.
- `pytest` - test runner.
- `pre-commit` - local commit hooks. Install with:

  ```bash
  uvx pre-commit install
  ```

- GitHub Actions - CI runs the same lint, format, and pytest checks on PRs.

## Testing

Root app tests live in `tests/test_*.py`.

Testing expectations:

- Add or update tests for new behavior in routes, database helpers, learning
  logic, conversation/tutor flows, or template helpers.
- Prefer pure unit tests for scheduling, BKT, prompt parsing, memory updates,
  and state transitions.
- Use FastAPI in-process tests for route behavior.
- Mock AI providers. Do not make live OpenAI or Anthropic calls in tests.
- Keep fixtures deterministic. Do not rely on a developer's existing
  `data/spanish_vibes.db` state.

Useful targeted commands:

```bash
uv run pytest tests/test_flow_routes.py
uv run pytest tests/test_tutor_memory.py tests/test_tutor_tools.py
uv run pytest -k conversation
```

If a task only touches the `app/` walking skeleton, run its local smoke loop from
`app/README.md` and do not assume the root-app pytest suite covers it.

## Working with AI Agents on This Repo

Success criteria are machine-checkable:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

Project-specific agent rules:

- Reference real code before relying on docs or implementation prompts.
- Do not rewrite prompt docs, personas, and route logic in the same PR unless
  the behavior needs all three.
- Keep root-app changes under `src/spanish_vibes/`, `templates/`, `content/`,
  `data/`, and `tests/` unless the task explicitly targets another area.
- Keep `app/` walking-skeleton work isolated from root-app work.
- Do not commit `.env`, API keys, raw learner submissions, personal memory
  files, or local DB churn.
- Treat tracked runtime files such as `data/spanish_vibes.db` as risky. Commit
  DB changes only when the task explicitly asks for a seed fixture or migration.
- When changing AI behavior, preserve deterministic offline fallbacks and tests.
- When changing templates, verify both regular and HTMX partial rendering paths.

## Security

- No fresh packages younger than 14 days. Pin to known-good versions or wait.
- Secrets stay in `.env` or the deployment provider's secret store.
- Do not log raw prompts, completions, API keys, learner notes, or personal
  submissions.
- Keep learner memory under ignored runtime paths unless a sanitized fixture is
  explicitly needed for a test.
- Prefer narrow dependency additions. If a standard-library or existing-package
  solution is reasonable, use it.

## Imported Claude Cowork project instructions
