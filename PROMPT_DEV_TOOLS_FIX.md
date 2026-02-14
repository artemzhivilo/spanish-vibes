# Dev Tools Panel — Fix Prompt

## Context

Read `PROMPT.md` for full project context. The dev tools panel already exists as an inline panel at the bottom of the flow page (`templates/partials/dev_panel.html`, included via `{% include "partials/dev_panel.html" %}` in `flow.html`). There's also a separate `/flow/dev` page (`flow_dev.html`) that duplicates most of this — we're removing that and consolidating everything into the inline panel.

**Current symptoms:** The current concept is always empty in the state display. Persona ID, conversation type, card ID are all empty. The state may not reload properly when answering cards. The state data is a raw JSON dump.

## Changes needed

### 1. Remove the separate dev page

Delete `templates/flow_dev.html` and remove the `/flow/dev` route from `flow_routes.py` (the `flow_dev_page` function, around line 118). Also remove the DEV link from `flow.html` header that points to `/flow/dev`:

```html
<!-- REMOVE this from flow.html header nav: -->
<a href="/flow/dev?session_id={{ session.id }}" class="rounded-full bg-slate-500/15 px-3 py-2 text-sm font-bold text-slate-300 transition hover:bg-slate-500/25">DEV</a>
```

The inline panel's toggle button (the fixed "DEV" button at bottom-right in `dev_panel.html`) is the only way to access dev tools now.

### 2. Fix the critical bug: dev state URL never includes card context

This is the main bug causing all the empty data.

**In `templates/partials/dev_panel.html` (around line 138):**
```html
<div id="dev-state-content"
     hx-get="/flow/dev/state?session_id={{ session.id }}"
     hx-trigger="load, cardChanged from:body"
     hx-swap="innerHTML">
```

The URL is **static** — `session_id` is baked in at template render time, and `concept_id` / `conversation_id` are never passed. So `_build_dev_state_payload()` always receives empty concept_id, and the "current concept" section is always empty.

**Fix:** Use `hx-vals` with a JS expression so HTMX evaluates the current card's data attributes fresh on every fetch:

```html
<div id="dev-state-content"
     hx-get="/flow/dev/state"
     hx-vals="js:{session_id: '{{ session.id }}', concept_id: (document.getElementById('flow-card-slot')?.dataset?.conceptId || ''), conversation_id: (document.getElementById('flow-card-slot')?.dataset?.conversationId || '0')}"
     hx-trigger="load, cardChanged from:body"
     hx-swap="innerHTML">
    Loading...
</div>
```

This works because `flow.html`'s `htmx:afterSwap` handler already:
1. Copies the hidden `data-dev-*` attributes from the card partial onto `#flow-card-slot`'s dataset
2. Then dispatches the `cardChanged` event

So by the time HTMX evaluates the `hx-vals` JS, the slot's `dataset.conceptId` is populated with the current card's concept.

### 3. Replace raw JSON state display with formatted HTML

**Current code in `flow_routes.py` (`_render_dev_state_html`, around line 1603):**
```python
def _render_dev_state_html(state: dict[str, Any]) -> str:
    pretty = json.dumps(state, indent=2, ensure_ascii=False)
    return "<div><strong>Engine State</strong><pre>" + escape(pretty) + "</pre></div>"
```

**Replace with** a function that builds labeled HTML sections. Use the panel's existing styling (`text-xs text-slate-200 font-mono`). Each section should be a div with a colored header and one-line-per-item data:

**CURRENT CONCEPT** (emerald header)
- Show: concept_id, name, p_mastery, attempts, correct/wrong, bucket (new/practice/spot-check), mastered yes/no
- If concept_id is empty, show "(none — card not loaded yet)"

**SESSION** (sky header)
- Show: cards answered, correct count, accuracy %, streak, conversations completed

**PERSONAS** (violet header)
- One line per persona: id, avg_enjoyment, conversation_count, novelty_bonus, selection_score_estimate
- Dim the excluded (last-used) persona with `text-slate-500`

**WORDS** (indigo header)
- Total tracked count
- Top tapped words with tap counts, inline: `hola(5) gato(3) entonces(2)`

**LAST EVALUATION** (amber header)
- Show: persona_id, conversation_type, engagement_quality, estimated_cefr
- Only show if evaluation data exists

**OVERRIDES** (orange header)
- List all active dev_overrides as key: value pairs
- Only show if any overrides exist

**ALL CONCEPTS** (slate header)
- One line per concept, sorted by tier then name
- Format: `[icon] concept_id    p_mastery  attempts  status`
- Icons/colors: ✅ emerald for MASTERED, 📚 amber for learning, 🆕 sky for new, 🔒 slate for locked
- Mark the current concept with `← current`

Use `border-t border-slate-700 pt-2 mb-3` between sections. No `<pre>` tags, no raw JSON. The point is scannable at a glance.

### 4. Clean up duplicate attribute sync

`dev_panel.html`'s script has a `syncCardMetaFromSlot()` function that duplicates the attribute sync already done in `flow.html`'s `htmx:afterSwap` handler. Since `flow.html` already syncs the attributes AND dispatches `cardChanged`, the duplicate in `dev_panel.html` is unnecessary.

The `saveFeedback()` function in `dev_panel.html` calls `syncCardMetaFromSlot()` before reading attributes — this is fine as a safety fallback. Keep `syncCardMetaFromSlot()` but just be aware it's a backup, not the primary sync mechanism.

## Files to modify

1. **`src/spanish_vibes/flow_routes.py`:**
   - Remove the `flow_dev_page` route handler (the `/flow/dev` GET endpoint)
   - Rewrite `_render_dev_state_html()` to produce formatted HTML sections

2. **`templates/partials/dev_panel.html`:**
   - Change `#dev-state-content` to use `hx-vals` with JS for dynamic concept_id/conversation_id

3. **`templates/flow.html`:**
   - Remove the DEV link from the header nav (the `<a href="/flow/dev?...">DEV</a>`)

## Files to delete

1. **`templates/flow_dev.html`** — no longer needed

## Testing

1. Open `/flow` → click DEV toggle button (bottom-right) → panel opens at bottom
2. Answer an MCQ card → state auto-refreshes → "CURRENT CONCEPT" shows the concept you just answered with mastery, attempts, bucket
3. Start a conversation → state shows persona_id and conversation_type populated
4. All sections render as labeled colored sections, NOT raw JSON
5. `/flow/dev` should 404 (route removed)
6. Verify the DEV link is gone from the flow header — only the toggle button remains
