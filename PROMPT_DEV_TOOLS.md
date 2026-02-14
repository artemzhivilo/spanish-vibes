# Dev Tools Panel — Implementation Prompt

## Context

Read `PROMPT.md` for full project context. This is a developer feedback tool — not user-facing. It helps the builder (you) see what the engine is doing and provide rapid feedback to tune the system. Don't worry about looks — function over form. Ugly is fine.

**The goal:** A collapsible panel visible during flow sessions that shows system state, lets you rate cards/conversations, flag issues, and see the engine's decision-making in real-time. Everything it captures gets stored in the DB for later analysis.

## What to build

### 1. Dev feedback table

Add to `db.py`:

```sql
CREATE TABLE IF NOT EXISTS dev_feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    card_type TEXT NOT NULL,          -- 'mcq', 'conversation', 'teach', 'word_intro', etc.
    card_id INTEGER,                   -- mcq_card_id or conversation_id
    concept_id TEXT,
    persona_id TEXT,
    conversation_type TEXT,
    rating INTEGER,                    -- 1-5 stars
    issue_tags TEXT,                   -- comma-separated: "ambiguous,wrong_answer,boring,too_easy,too_hard,personality_off,bad_grammar"
    note TEXT,                         -- free-text feedback
    context_json TEXT,                 -- snapshot of system state at time of feedback
    created_at TEXT NOT NULL
);
```

The `context_json` field stores a snapshot of what the engine was thinking: concept mastery, persona selection weights, enjoyment scores, evaluation results, etc. This is the gold — it lets you correlate "this felt wrong" with the actual system state.

### 2. Dev feedback endpoint

Add to `flow_routes.py`:

```python
@router.post("/flow/dev/feedback", response_class=HTMLResponse)
async def dev_feedback(
    request: Request,
    card_type: str = Form(...),
    card_id: int = Form(default=0),
    concept_id: str = Form(default=""),
    persona_id: str = Form(default=""),
    conversation_type: str = Form(default=""),
    rating: int = Form(default=0),
    issue_tags: str = Form(default=""),
    note: str = Form(default=""),
    context_json: str = Form(default="{}"),
) -> Response:
    """Store dev feedback for the current card/conversation."""
    # Insert into dev_feedback table
    # Return a small "✓ Saved" confirmation div
```

### 3. Dev state endpoint

Add to `flow_routes.py`:

```python
@router.get("/flow/dev/state", response_class=HTMLResponse)
async def dev_state(
    request: Request,
    session_id: int = Query(...),
    concept_id: str = Query(default=""),
    conversation_id: int = Query(default=0),
) -> Response:
    """Return current engine state as an HTML fragment for the dev panel."""
```

This endpoint gathers and returns:

**Concept state:**
- Current concept_id, name, p_mastery, n_attempts, n_correct, n_wrong
- Is it mastered? How far from mastery?
- Which bucket did card selection pull from (spot-check/practice/new)?

**Persona state (if conversation):**
- Which persona was selected and why
- Engagement scores for all personas (show the selection weights)
- Novelty bonuses
- Which persona was excluded (last used)

**Word tracking:**
- Total words tracked, words added this session
- Most-tapped words (top 5)
- Words harvested from last conversation

**Evaluation results (if conversation just ended):**
- Concepts demonstrated (concept_id, correct/incorrect counts)
- Vocabulary extracted
- User facts discovered
- Persona observations
- Engagement quality score
- CEFR estimates

**Session stats:**
- Cards answered this session
- Conversations completed
- Current streak / accuracy

Return this as a simple HTML fragment — just key-value pairs, no styling needed beyond basic readability.

### 4. Dev panel UI

Add a collapsible dev panel to the flow page. It should be:
- Always present during a flow session (when on `/flow`)
- Collapsed by default, toggle with a button
- Positioned as a bottom panel or sidebar — doesn't matter, whatever's easiest
- Loads state via HTMX after each card is served

**In `templates/flow.html` (or a new partial `templates/partials/dev_panel.html`):**

```html
<!-- Dev Tools Toggle -->
<button id="dev-toggle" onclick="document.getElementById('dev-panel').classList.toggle('hidden')"
    class="fixed bottom-2 right-2 z-50 bg-gray-800 text-gray-400 text-xs px-2 py-1 rounded">
    DEV
</button>

<!-- Dev Panel -->
<div id="dev-panel" class="hidden fixed bottom-0 left-0 right-0 z-40 bg-gray-900 border-t border-gray-700 max-h-[40vh] overflow-y-auto p-3 text-xs text-gray-300 font-mono">

    <!-- Quick Feedback Row -->
    <div id="dev-feedback-section">
        <strong>Rate this card:</strong>
        <!-- 5 star buttons, each posts to /flow/dev/feedback -->
        <button hx-post="/flow/dev/feedback" hx-vals='{"rating": 1, ...}'>1</button>
        <button hx-post="/flow/dev/feedback" hx-vals='{"rating": 2, ...}'>2</button>
        <button hx-post="/flow/dev/feedback" hx-vals='{"rating": 3, ...}'>3</button>
        <button hx-post="/flow/dev/feedback" hx-vals='{"rating": 4, ...}'>4</button>
        <button hx-post="/flow/dev/feedback" hx-vals='{"rating": 5, ...}'>5</button>

        <!-- Issue tag checkboxes -->
        <label><input type="checkbox" value="ambiguous"> Ambiguous</label>
        <label><input type="checkbox" value="too_easy"> Too easy</label>
        <label><input type="checkbox" value="too_hard"> Too hard</label>
        <label><input type="checkbox" value="boring"> Boring</label>
        <label><input type="checkbox" value="wrong_answer"> Wrong answer</label>
        <label><input type="checkbox" value="personality_off"> Personality off</label>
        <label><input type="checkbox" value="bad_grammar"> Bad grammar</label>

        <!-- Free text note -->
        <input type="text" id="dev-note" placeholder="Quick note..." class="bg-gray-800 text-gray-300 px-2 py-1 rounded text-xs w-64">

        <!-- Submit -->
        <button id="dev-submit-feedback">Save</button>
        <span id="dev-feedback-confirmation"></span>
    </div>

    <hr class="border-gray-700 my-2">

    <!-- Engine State (loaded via HTMX) -->
    <div id="dev-state-content"
         hx-get="/flow/dev/state?session_id={{ session_id }}"
         hx-trigger="load, cardChanged from:body"
         hx-swap="innerHTML">
        Loading...
    </div>
</div>
```

The key UX detail: the feedback section needs to know WHICH card it's rating. The current card's metadata (card_type, card_id, concept_id, persona_id, conversation_type) should be available as hidden fields or data attributes. These get set each time a new card loads.

**Approach:** When `flow_card` renders a new card, include hidden data attributes on the card container that the dev panel JS reads:

```html
<div id="flow-card-slot"
     data-card-type="{{ card_context.card_type }}"
     data-card-id="{{ card_context.mcq_card_id or '' }}"
     data-concept-id="{{ card_context.concept_id }}"
     data-persona-id="{{ persona_id or '' }}"
     data-conversation-type="{{ conversation_type or '' }}">
```

The dev panel JS reads these when submitting feedback.

### 5. Quick actions

Add a few buttons to the dev panel for common dev operations:

```html
<!-- Quick Actions -->
<div>
    <strong>Actions:</strong>
    <button hx-post="/flow/clear-mcq-cache" hx-target="#dev-feedback-confirmation">Clear MCQ cache</button>
    <button hx-post="/flow/dev/reset-concept" hx-vals='{"concept_id": "..."}'>Reset concept</button>
    <button hx-post="/flow/dev/force-persona" hx-vals='{"persona_id": "diego"}'>Force Diego next</button>
    <button hx-post="/flow/dev/force-conversation">Force conversation next</button>
</div>
```

Endpoints for quick actions:

```python
@router.post("/flow/dev/reset-concept")
# Reset a concept's BKT state to 0 (re-learn from scratch)

@router.post("/flow/dev/force-persona")
# Set a session-level override so the next conversation uses a specific persona

@router.post("/flow/dev/force-conversation")
# Set a flag so the next card is always a conversation (skip MCQ/teach)
```

These are dev-only — store the overrides in a simple session-level dict or a `dev_overrides` table. They don't need to be persistent across server restarts.

### 6. Evaluation results display

After a conversation summary, the evaluation results should be visible in the dev panel. Two approaches:

**Option A (simpler):** Store the last evaluation result in a module-level variable and serve it via `/flow/dev/state`. Gets overwritten each time.

**Option B (better):** Store evaluation JSON in the `flow_conversations` table (new column `evaluation_json`). The dev state endpoint reads it. This also gives you historical evaluation data for analysis.

Go with Option B:

```sql
-- Add to flow_conversations ALTER TABLE section:
if "evaluation_json" not in conv_cols:
    connection.execute("ALTER TABLE flow_conversations ADD COLUMN evaluation_json TEXT")
```

Store the full evaluation result as JSON after each conversation. The dev panel reads and displays it.

### 7. Engine tuning controls

The most important part of the dev panel — the ability to change the inputs and weights that drive card selection in real-time.

**a) Level / tier selector:**

There's already a `skip-to-tier` endpoint that mass-marks concepts below a tier as mastered. Expose this in the dev panel as a dropdown:

```html
<strong>Set level:</strong>
<select id="dev-tier-select">
    <option value="1">Tier 1 (A1 basics)</option>
    <option value="2">Tier 2 (A1 full)</option>
    <option value="3">Tier 3 (A2)</option>
</select>
<button hx-post="/flow/skip-to-tier" hx-include="#dev-tier-select">Jump to tier</button>
```

Also add a "Reset to zero" button that clears ALL concept knowledge — start completely fresh.

```python
@router.post("/flow/dev/reset-all")
# DELETE FROM concept_knowledge; DELETE FROM flow_sessions; etc.
# Nuclear option — wipes all progress
```

**b) Bucket weight sliders:**

Currently hardcoded in `flow.py`:
```python
WEIGHT_SPOT_CHECK = 0.30  # mastered concepts
WEIGHT_PRACTICE = 0.50    # learning concepts
WEIGHT_NEW = 0.20         # new concepts
```

Add a `dev_overrides` table to make these tunable:

```sql
CREATE TABLE IF NOT EXISTS dev_overrides (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

Store overrides like:
- `bucket_weight_spot_check`: "0.30"
- `bucket_weight_practice`: "0.50"
- `bucket_weight_new`: "0.20"
- `conversation_frequency`: "5" (every N MCQ cards)
- `force_next_persona`: "diego" (one-shot override, cleared after use)
- `force_next_card_type`: "conversation" (one-shot override)
- `force_next_conversation_type`: "role_play" (one-shot override)

In the dev panel, show three range inputs for bucket weights:

```html
<strong>Card selection weights:</strong>
<label>Spot-check (mastered): <input type="range" min="0" max="100" value="30" id="w-spot"> <span>30%</span></label>
<label>Practice (learning): <input type="range" min="0" max="100" value="50" id="w-practice"> <span>50%</span></label>
<label>New concepts: <input type="range" min="0" max="100" value="20" id="w-new"> <span>20%</span></label>
<button hx-post="/flow/dev/set-weights" hx-include="[id^=w-]">Apply</button>
```

Modify `flow.py` `_pick_concept()` to check for overrides before using the hardcoded constants:

```python
def _get_bucket_weights() -> tuple[float, float, float]:
    """Load bucket weights from dev_overrides, falling back to defaults."""
    try:
        overrides = _load_dev_overrides()  # reads dev_overrides table
        spot = float(overrides.get("bucket_weight_spot_check", WEIGHT_SPOT_CHECK))
        practice = float(overrides.get("bucket_weight_practice", WEIGHT_PRACTICE))
        new = float(overrides.get("bucket_weight_new", WEIGHT_NEW))
        return spot, practice, new
    except Exception:
        return WEIGHT_SPOT_CHECK, WEIGHT_PRACTICE, WEIGHT_NEW
```

**c) Conversation frequency control:**

```html
<strong>Conversation every N cards:</strong>
<input type="number" min="1" max="20" value="5" id="conv-freq">
<button hx-post="/flow/dev/set-override" hx-vals='{"key": "conversation_frequency"}' hx-include="#conv-freq">Set</button>
```

Modify the conversation injection logic in `flow.py` to read this override.

**d) Force next card type:**

Dropdown to force the next card to be a specific type:

```html
<strong>Force next card:</strong>
<select id="force-card-type">
    <option value="">Auto</option>
    <option value="mcq">MCQ</option>
    <option value="conversation">Conversation</option>
    <option value="teach">Teach</option>
    <option value="word_intro">Word intro</option>
    <option value="word_practice">Word practice</option>
    <option value="story_comprehension">Story comprehension</option>
</select>
<button hx-post="/flow/dev/set-override" hx-vals='{"key": "force_next_card_type"}' hx-include="#force-card-type">Force</button>
```

One-shot: the override is consumed and cleared when the next card is selected.

**e) Force conversation type:**

```html
<strong>Force conversation type:</strong>
<select id="force-conv-type">
    <option value="">Auto</option>
    <option value="general_chat">General chat</option>
    <option value="role_play">Role play</option>
    <option value="concept_required">Concept required</option>
    <option value="tutor">Tutor</option>
    <option value="story_comprehension">Story comprehension</option>
</select>
```

**f) Force persona:**

```html
<strong>Force persona:</strong>
<select id="force-persona">
    <option value="">Auto</option>
    <!-- Populated from loaded personas -->
    <option value="marta">Marta</option>
    <option value="diego">Diego</option>
    <option value="abuela_rosa">Abuela Rosa</option>
    <option value="luis">Luis</option>
</select>
```

**g) Force concept:**

Dropdown of all concepts, sorted by tier. Forces the next card to use a specific concept regardless of BKT state.

```html
<strong>Force concept:</strong>
<select id="force-concept">
    <option value="">Auto</option>
    <!-- Populated from concepts.yaml -->
</select>
```

### 8. Concept mastery overview

In the dev state panel, show a compact overview of ALL concepts and their current state:

```
CONCEPT              p_mastery  attempts  status
greetings            0.95       12        MASTERED
ser_estar            0.42       8         learning
preterite_regular    0.15       3         learning
subjunctive          0.00       0         locked (prereq: preterite)
```

This gives you a bird's-eye view of where you are in the curriculum without leaving the flow page. Color-code or mark the currently active concept.

## What NOT to build

- No auth/protection — this is dev-only, no need to hide it behind a flag yet
- No fancy charts or graphs — just raw data in monospace text
- No feedback analysis dashboard — just store it, analyze manually or in a future iteration
- No mobile optimization — this is a desktop dev tool

## Files to create

1. `templates/partials/dev_panel.html` — Dev panel HTML partial

## Files to modify

1. `src/spanish_vibes/db.py` — Add `dev_feedback` table, `dev_overrides` table, add `evaluation_json` column to `flow_conversations`
2. `src/spanish_vibes/flow_routes.py` — Add `/flow/dev/feedback`, `/flow/dev/state`, `/flow/dev/set-weights`, `/flow/dev/set-override`, `/flow/dev/reset-all`, `/flow/dev/reset-concept` endpoints
3. `src/spanish_vibes/flow.py` — Modify `_pick_concept()` to read bucket weights from `dev_overrides`, modify conversation injection to read frequency override, check for force overrides (card type, concept)
4. `src/spanish_vibes/personas.py` — Check for `force_next_persona` override in `select_persona()`
5. `templates/flow.html` — Include the dev panel partial
6. `templates/partials/flow_card.html` — Add data attributes for current card metadata

## Testing

- Verify feedback saves to DB with correct card metadata
- Verify dev state endpoint returns current concept/persona/word data
- Verify panel toggles open/closed
- Verify state refreshes when a new card loads
- Verify quick actions work (clear cache, reset concept, force persona)
- Verify evaluation JSON is stored and displayed for conversations
- Verify bucket weight sliders change card selection behavior
- Verify force overrides work (card type, persona, concept, conversation type) and are consumed after one use
- Verify tier jump works from the panel
- Verify reset-all wipes progress cleanly
- Verify concept mastery overview shows all concepts with correct status
