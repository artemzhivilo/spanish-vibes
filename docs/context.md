# Project: Spanish Vibes (A2 Trainer)

## Tech stack (locked)
- Python 3.11+
- FastAPI (server + routes)
- Jinja templates (server-rendered UI)
- HTMX (progressive interactivity, no heavy SPA)
- Tailwind via CDN (no build step initially)
- SQLite (file DB)

## App scope (MVP)
- Deck management: add card (front: ES, back: EN, example: optional)
- Quiz loop: Show → Reveal → Grade (Good/Again)
- Spaced repetition: SM-2-ish
  - FAST MODE: intervals in minutes for rapid feedback
  - DAY MODE: switchable later (env flag or constant)
- Home: due count + “Start quiz”, add form, recent cards
- Quiz panel loads/updates via HTMX swaps (no full refresh)

## OpenAI integration (guardrails)
- Use OpenAI **Responses API** to generate candidate cards and example sentences.
- Inputs we control: level (A1/A2), grammar focus (e.g., “pretérito vs. imperfecto”, “gustar”, “por/para”), lexical themes (“directions”, “daily routines”).
- Outputs we require: JSON schema {spanish, english, example, tag}.
- **No copyrighted content**: never copy from third-party sources (including my textbook); generate original examples.
- **Safety**: refuse named, copyrighted song/film/book quotes.

## Quality & DX
- Type hints, small functions, short modules
- Minimal Jinja includes/partials for table rows and quiz panel
- Tiny tests for scheduler logic (intervals, ease, due ordering)
- Ruff lint (reasonable defaults), Makefile tasks: run, test, lint, fmt
- No global singletons besides a small sqlite helper
- Keep code concise; nice Tailwind defaults; accessible buttons/labels

## Nice-to-haves (post-MVP)
- Tags + filtered quiz
- CSV import/export
- TTS for Spanish on reveal
- Type-in answer mode (validate before reveal)