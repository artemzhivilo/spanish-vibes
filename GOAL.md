# /goal — Spanish Vibes: Phase 2 Build-Out

You are building out the Phase 1 walking skeleton in `app/` into a polished, persistent, multi-persona Spanish learning app. The legacy code in `src/spanish_vibes/` is reference material — mine it for ideas and algorithms but do NOT import from it. Everything lives in `app/`.

Read `ENGINE_OVERVIEW.md`, `DESIGN_IDEAS.md`, `PROMPT_FOR_CLAUDE_DESIGN.md`, and `BACKLOG.md` before starting. They contain detailed design decisions you should follow.

## The Vibe (read this first)

This is NOT Duolingo. No owls, no gems, no streaks, no "+5 XP" floaters. It's the experience of texting a Spanish friend who happens to be a teacher. The chat is the entire product. Activities appear inline in the conversation like a friend handing you a napkin — they don't take over the screen.

Visual mood: warm messaging app. Off-white background, warm dark text, terracotta/muted amber accent. Closer to iMessage than any learning app. Generous whitespace. Subtle motion (bubbles fade-rise, cards slide in). "Smart adult app" aesthetic.

## What to build (in priority order)

### 1. Visual Design & Mobile-First UI

The app currently has minimal styling. Transform it into something beautiful that feels like a premium messaging app.

**Chat interface:**
- Mobile-first layout (~390px), works on desktop too
- User bubbles right-aligned in accent color, persona bubbles left-aligned with small avatar and faintly tinted background
- Each persona gets a slightly different bubble tint so switching personas feels distinct
- Rounded, friendly sans-serif typography for chat
- Generous spacing — one thought per bubble, whitespace matters
- Smooth animations: bubbles fade and rise into place, exercise cards slide in
- Input bar at bottom, sticky, with send button

**Exercise cards inline:**
- Fill-in-blank cards sit inline between chat bubbles, not full-screen takeover
- Compact design — each blank is a small input field within the sentence
- Correct answers get a subtle glow for half a beat, wrong answers show the correct word gently
- After completing, persona sends a reaction message naturally

**Overall layout:**
- No navigation tabs in Phase 2. The chat IS the app
- Persona switcher: a small avatar/name in the top bar that opens a drawer/sheet showing all 4 personas as cards with "last chatted" info
- Clean top bar with persona name + avatar, nothing else

Use Tailwind CSS via CDN for styling. Keep all CSS in the HTML templates or a single stylesheet. No build step.

### 2. Persistence with SQLite

Replace all in-memory state with SQLite so progress survives server restarts.

**Schema (create `app/db.py`):**
- `conversations` table: id, learner_id, persona_id, started_at, ended_at, messages (JSON)
- `exercises` table: id, conversation_id, learner_id, exercise_type, data (JSON), results (JSON), created_at
- `learner_progress` table: learner_id, concept_id, p_mastery (float), attempts (int), last_practiced
- `learner_profile` table: learner_id, key, value, confidence, updated_at
- `persona_memories` table: id, persona_id, learner_id, memory_text, importance (float), created_at

Database file at `app/data/spanish_vibes.db`. Create migration/init function that runs on startup. Use Python's built-in `sqlite3` — no ORM needed.

**What changes in main.py:**
- `HISTORY` dict → load/save from `conversations` table
- `QUIZZES` dict → load/save from `exercises` table
- `save_learner_notes` tool → also write structured data to `learner_profile` and `persona_memories`
- On startup, load the most recent conversation for the learner if it exists

### 3. Multi-Persona System

Add Diego, Abuela Rosa, and Luis alongside Marta. Each persona is a markdown file in `app/personas/` following the same format as `marta.md`.

**Persona definitions (write these persona files with real personality):**

- **Diego** (`diego.md`) — 22-year-old football-obsessed uni student in Barcelona. Uses "tío" constantly, slang-heavy, high energy, competitive. Uses **tú**. Corrects by repeating correctly but adds "jajaja" or teases lightly. Talks about fútbol, gaming, going out. Voice: *"Tío, ayer el partido fue una locura, ¿lo viste?"*

- **Abuela Rosa** (`rosa.md`) — 68-year-old grandmother in a small town near Granada. Warm, talks about cooking and family, uses traditional expressions and refranes (proverbs). Uses **tú** but sometimes slips into **usted** territory with formal expressions. Shares recipes, family stories, life wisdom. Voice: *"Mi vida, ¿has comido algo rico hoy?"*

- **Luis** (`luis.md`) — 29-year-old tech startup founder in Madrid. Talks fast, mixes in English loanwords ("meeting", "deadline", "feedback"), slightly sarcastic, always busy. Uses **tú**. Corrects efficiently, no fluff. Talks about work, tech, Madrid nightlife, travel. Voice: *"Ostras, hoy tuvimos un meeting eterno con el equipo de product."*

**Each persona file must include:**
- A vivid character description (age, city, personality, speaking style)
- How they reply (length, language mix, correction style — each distinct)
- How they use the tools (each persona uses exercises differently — Diego makes them competitive, Rosa makes them about cooking vocab, Luis keeps them quick)
- The `{learner_notes}` injection slot

**Persona selection in the app:**
- Add a `persona_id` parameter to `run_agent_turn()` and all related functions
- Store current persona in session state
- Build the persona switcher UI — top bar shows current persona avatar + name, tapping opens a drawer with all 4 personas
- When switching personas, start a new conversation but carry over learner notes
- Each persona reads the same learner notes file but writes their own observations

### 4. More Exercise Types

Add two new tool types beyond `create_fill_in_blank`:

**`create_flashcard_set`** — A swipeable set of 4-6 word cards the persona wants the learner to look at. Each card has Spanish on front, English + emoji on back. Rendered inline as a compact horizontal card stack. User taps to flip, swipes/clicks arrow to advance. After viewing all, persona continues chatting.

**`create_grammar_explainer`** — A clean inline card with a grammar rule title, two example sentences (with the pattern bolded), and one sentence of plain-language explanation. Optional "show more" expander for additional examples. Used when the learner keeps making the same mistake and a gentle in-flow explanation would help.

Add these to the `TOOLS` list in main.py with proper schemas, handle them in the agent loop, and create the HTMX partial templates. Update each persona's prompt to explain when/how to use them (each persona uses them differently).

### 5. Session Summary

When the learner says goodbye and the persona calls `save_learner_notes`:

After the farewell message, render a session summary card at the bottom of the chat. Quiet, generous layout:
- A one-line note: "23-minute chat with Marta" (calculate from conversation start time)
- "Words you practiced" — small chips showing Spanish words that came up in exercises
- "Things to revisit" — 1-2 grammar points from mistakes made
- "What [Persona] noticed" — 1-2 lines from the notes about what they learned about the learner

Design this as an inline card at the bottom of the chat, consistent with the overall aesthetic. No XP, no streaks, no gamification.

### 6. Conversation History

When the app loads, show the most recent conversation with each persona (or a "Start chatting" prompt if it's the first time). When switching personas, show their last conversation scrolled to the bottom, with a visual divider and "Continue chatting..." prompt.

This requires:
- Saving full message history to SQLite (not just learner notes)
- Loading and rendering previous messages on page load
- A visual "session break" divider between conversations on different days/sessions

### 7. Better Answer Validation

The current `is_correct()` strips accents and compares. Improve it:
- Accept common typos (one character off)
- Accept answers with/without accent marks but flag when accents were wrong: "Correct! But note the accent: está not esta"
- For fill-in-blank: if the answer is close but wrong, show what they wrote vs the correct answer side by side

## Technical constraints

- **Stack**: FastAPI + HTMX + Jinja2 + Tailwind CSS (via CDN). No React, no npm, no build step.
- **Python venv**: use the existing `app/.venv`. Activate it before running. Use `uv` for package management if adding deps.
- **Database**: SQLite via Python's `sqlite3`. No SQLAlchemy.
- **AI**: Anthropic SDK, `claude-opus-4-7` with `thinking: {"type": "adaptive"}`. Keep prompt caching.
- **Single user**: keep `LEARNER_ID = "artem"` for now. Multi-user auth is Phase 3.
- **No new directories outside `app/`**: everything lives in the `app/` directory.

## How to verify your work

After each major section, run the app (`cd app && uv run uvicorn main:app --reload`) and verify:
1. The chat loads and looks beautiful on mobile viewport (use browser dev tools, 390px wide)
2. You can chat with Marta and she responds naturally
3. You can switch to another persona and they greet you in character
4. Exercise cards render inline and work (fill-in-blank, flashcards, grammar explainer)
5. Restart the server — conversation history and learner notes persist
6. The session summary appears when you say goodbye

## Files to create/modify

**New files:**
- `app/db.py` — SQLite database layer
- `app/personas/diego.md` — Diego persona
- `app/personas/rosa.md` — Abuela Rosa persona
- `app/personas/luis.md` — Luis persona
- `app/templates/partials/flashcard_set.html` — flashcard exercise template
- `app/templates/partials/grammar_explainer.html` — grammar explainer template
- `app/templates/partials/session_summary.html` — session summary template
- `app/templates/partials/persona_switcher.html` — persona drawer template

**Modify:**
- `app/main.py` — add new tools, persona switching, SQLite integration, session tracking
- `app/templates/index.html` — visual redesign, persona switcher, layout
- `app/templates/partials/turn.html` — styled chat bubbles with persona-specific tints
- `app/templates/partials/quiz_feedback.html` — improved answer feedback
- `app/static/style.css` — may keep minimal custom CSS alongside Tailwind

Start with visual design (#1), then persistence (#2), then personas (#3), then work through the rest in order. Commit after each major section with a descriptive message.
