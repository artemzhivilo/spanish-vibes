# PROMPT 16 — Gap-Fill / Cloze Activity Type

## Context

Spanish Vibes is a FastAPI + Jinja2 + HTMX + Tailwind + SQLite language learning app with an agent-based tutor system. The tutor uses a two-tier LLM architecture:

- **Planner** (gpt-5.2): decides what activity to run next via tool-calling
- **Workers** (gpt-5-mini): execute individual activities (conversation, evaluation)
- **Local evaluation**: conjugation drills are checked server-side, no LLM needed

### Current Activity Types

| Tool name | What it does | Evaluation |
|---|---|---|
| `start_conversation` | Free-form Spanish conversation with a persona | Worker LLM scores grammar + communication |
| `show_conjugation_drill` | Rapid-fire "yo + hablar = ?" conjugation | Server-side exact match (with accent tolerance) |
| `show_translation_challenge` | English → Spanish sentence translation | Worker LLM evaluates |
| `show_circumlocution_challenge` | Express complex ideas with simple Spanish | Worker LLM evaluates communication + resourcefulness |

### What's Missing

Analysis of the **Aula Internacional Plus 2 (A2)** textbook reveals that **cloze / gap-fill exercises** are the single most common exercise type in professional Spanish pedagogy. Every unit uses them extensively for:

- Verb conjugation **in context** ("María _____ (vivir) en Barcelona desde hace dos años")
- Preposition selection ("Estudio español _____ conseguir un trabajo mejor" — por/para)
- Ser vs. estar ("La fiesta _____ en mi casa" / "Mi hermano _____ alto")
- Article and gender agreement ("_____ problema es que no tengo tiempo")
- Vocabulary in context ("Me siento _____ cuando hablo en público" — ridículo/inseguro/bien)

The current conjugation drill is decontextualized ("yo + tener = ?"). A gap-fill puts the same grammar into a real sentence, which is pedagogically far more effective for transfer to actual speech.

---

## Task

Add a new `show_cloze_exercise` tool to the tutor system. This is a gap-fill activity where the learner sees Spanish sentences with blanks and must fill in the correct word/form.

### Architecture Requirements

Follow the exact same patterns as existing activity types. Specifically:

**1. Tool schema** (`tutor_agent.py` → `TOOL_SCHEMAS` list)

Add a new entry:

```python
{
    "type": "function",
    "function": {
        "name": "show_cloze_exercise",
        "description": (
            "Gap-fill exercise: learner sees Spanish sentences with blanks and types "
            "the missing word. Evaluated SERVER-SIDE (no LLM needed) for exact-match "
            "items, or by WORKER LLM for open-ended fills. "
            "Much more effective than isolated conjugation drills because grammar "
            "is practised IN CONTEXT. Use for: verb conjugation in sentences, "
            "preposition choice (por/para, a/en/de), ser vs estar, article agreement, "
            "vocabulary in context. "
            "Ideal after a conversation or drill to consolidate a specific form."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "tutor_message": {
                    "type": "string",
                    "description": "Brief intro before the exercise (1-2 sentences)",
                },
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "sentence": {
                                "type": "string",
                                "description": (
                                    "Spanish sentence with exactly ONE blank marked as ___. "
                                    "Include a hint in parentheses if needed: "
                                    "'María ___ (vivir) en Barcelona desde hace dos años.' "
                                    "The hint tells the learner what to conjugate/choose."
                                ),
                            },
                            "answer": {
                                "type": "string",
                                "description": "The correct fill (e.g. 'vive'). Lowercase, no punctuation.",
                            },
                            "accept_also": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": (
                                    "Alternative correct answers (e.g. for 'está' also accept 'esta' "
                                    "as an accent-tolerant match). Include common valid variants."
                                ),
                            },
                            "explanation": {
                                "type": "string",
                                "description": (
                                    "Brief explanation shown after answering (right or wrong). "
                                    "E.g. 'vivir → vive (3rd person singular present)'"
                                ),
                            },
                        },
                        "required": ["sentence", "answer"],
                    },
                    "description": "4-8 gap-fill items. Each has one blank.",
                },
                "target_grammar": {
                    "type": "string",
                    "description": "Grammar concept being tested (e.g. 'present_tense', 'por_para', 'ser_estar')",
                },
                "difficulty": {
                    "type": "integer",
                    "description": "1-3. Affects hint visibility and strictness.",
                },
                "worker_briefing": {
                    "type": "string",
                    "description": "Context: what the learner struggles with, why these items were chosen.",
                },
            },
            "required": ["tutor_message", "items", "target_grammar", "worker_briefing"],
        },
    },
}
```

**2. Tool implementation** (`tutor_tools.py`)

Add `tool_show_cloze_exercise(params, session) -> ToolResult`:

- Extract items from params, validate each has `sentence` and `answer`
- Render the first item using a new template `partials/tutor_activity_cloze.html`
- Store items as hidden JSON (same pattern as drill/translation)
- Return `ToolResult` with html and activity_data

Add `render_cloze_answer(...)` function:

- Compare user input to `answer` (case-insensitive, strip whitespace)
- Also check `accept_also` list
- Accent-tolerant matching (same `_check_conjugation` logic from drills — strip accents for comparison, flag accent-only mismatches)
- Show feedback: ✓ correct / ≈ accent slip / ✗ wrong (show correct answer + explanation)
- Advance to next item or show completion card
- Completion card: score percentage, list of missed items with explanations, "Continue →" button

**3. HTML template** (`templates/partials/tutor_activity_cloze.html`)

Follow the visual style of `tutor_activity_drill.html`:

- Activity card with header badge "📝 Fill in the blank"
- Progress bar at top (same as drill)
- The sentence displayed prominently with the blank highlighted (use an underline or colored placeholder)
- Hint in parentheses shown in a muted color
- Text input for the answer
- "Check →" button
- After answering: feedback block (green/yellow/red) with explanation, then auto-advance

The sentence display should render the blank as a visually distinct element:
```
María _______ en Barcelona desde hace dos años.
        (vivir)
```

**4. Route** (`tutor_routes.py`)

Add two endpoints following the drill pattern:

```python
@router.post("/cloze/answer", response_class=HTMLResponse)
async def post_cloze_answer(
    session_id: Annotated[str, Form()],
    items_json: Annotated[str, Form()],
    current_index: Annotated[int, Form()],
    correct_count: Annotated[int, Form()],
    errors_json: Annotated[str, Form()] = "[]",
    user_answer: Annotated[str, Form()] = "",
) -> HTMLResponse:
    """Process one cloze answer and render next item or completion."""
    ...

@router.post("/cloze/complete", response_class=HTMLResponse)
async def post_cloze_complete(
    session_id: Annotated[str, Form()],
    score: Annotated[float, Form()],
    errors_json: Annotated[str, Form()] = "[]",
    total: Annotated[int, Form()] = 0,
    target_grammar: Annotated[str, Form()] = "",
) -> HTMLResponse:
    """Record cloze results and ask planner for next activity."""
    ...
```

The `/cloze/complete` route should:
1. Record the activity in `session.activities`
2. Log to the debug panel
3. Call `session.plan_next_action()` for the next activity
4. Return the planner's next action result HTML

**5. CSS** (`tutor.html` `<style>` block)

Add styles for the cloze activity. Key elements:
- `.cloze-badge` — similar to `.drill-badge` but different color (e.g. indigo/blue)
- `.cloze-sentence` — the full sentence with blank, large readable font
- `.cloze-blank` — the blank itself, underlined or highlighted
- `.cloze-hint` — the parenthetical hint, muted color, smaller
- `.cloze-input` — text input styled like `.drill-input`
- `.cloze-feedback-block` — same pattern as drill feedback blocks

**6. Planner system prompt update** (`tutor_agent.py` → `_PLANNER_SYSTEM`)

Add to the ACTIVITY VARIETY section:

```
5. CLOZE / GAP-FILL: Grammar in context. Much more effective than isolated
   drills. Use to test verb forms in real sentences, preposition choice,
   ser/estar, article agreement. Ideal after a drill to test transfer,
   or before conversation to prime specific forms.
   Progression: drill → cloze → conversation (isolated → in-context → free production)
```

Update the NEW LEARNER SESSION FLOW if appropriate (cloze could replace or supplement the translation challenge for absolute beginners).

Update PEDAGOGICAL PRINCIPLES to mention the drill → cloze → conversation progression.

**7. Thinking indicator** (`tutor.html` JS)

Add `/tutor/cloze/complete` to the list of paths that show the thinking indicator:

```javascript
if (path && (path.includes('/tutor/conversation/complete')
             || path.includes('/tutor/drill/complete')
             || path.includes('/tutor/cloze/complete')
             || ...
```

---

### Design Decisions

**Server-side evaluation (no LLM):** Since cloze items have a known correct answer (provided by the planner), we can evaluate them locally like conjugation drills. This makes the activity fast and cheap. The planner (expensive model) generates the items; evaluation is just string comparison.

**Answer matching logic:**
1. Exact match (case-insensitive, trimmed)
2. Check `accept_also` list
3. Accent-tolerant: strip diacritics for comparison (á→a, ñ→n, ü→u), flag as "accent slip" if base matches but accent differs
4. Wrong: show correct answer + explanation

**Item generation by the planner:** The planner generates items tailored to the learner's current weakness. Example — if grammar_notes say "confuses ser/estar with location", the planner generates:

```json
{
  "items": [
    {"sentence": "La fiesta ___ en mi casa.", "answer": "es", "explanation": "Events use 'ser' for location: la fiesta es en mi casa."},
    {"sentence": "Mi hermano ___ en el supermercado.", "answer": "está", "explanation": "People's temporary location uses 'estar'."},
    {"sentence": "¿Dónde ___ el restaurante?", "answer": "está", "explanation": "Physical location of a place uses 'estar'."},
    {"sentence": "La reunión ___ a las tres.", "answer": "es", "explanation": "Scheduled events use 'ser'."}
  ]
}
```

**No answers leaked to the client:** Store `answer`, `accept_also`, and `explanation` server-side only. The hidden `items_json` sent to the client should strip these fields. On each answer submission, the server looks up the correct answer from the full items list (same security pattern as conjugation drills).

---

### Files to Modify

| File | Changes |
|---|---|
| `src/spanish_vibes/tutor_agent.py` | Add tool schema to `TOOL_SCHEMAS`, update `_PLANNER_SYSTEM` |
| `src/spanish_vibes/tutor_tools.py` | Add `tool_show_cloze_exercise()`, `render_cloze_answer()`, register in `_TOOL_MAP` |
| `src/spanish_vibes/tutor_routes.py` | Add `/cloze/answer` and `/cloze/complete` routes |
| `templates/partials/tutor_activity_cloze.html` | New template for the cloze card |
| `templates/tutor.html` | Add CSS for cloze styles, add `/cloze/complete` to thinking indicator paths |

### Testing

After implementation:
1. Start the app, open the tutor
2. The planner should start offering cloze exercises as part of its activity rotation
3. Verify: items display correctly, input works, answer checking works (correct, accent slip, wrong), completion card shows, "Continue →" triggers planner for next activity
4. Verify: dev panel shows the cloze tool call with items
5. Verify: session end screen includes cloze activities in the summary

### Example Session Arc (post-implementation)

```
Planner: "Let's warm up with a quick conjugation drill on present tense."
→ show_conjugation_drill (isolated forms)

Planner: "Nice! Now let's see those forms in real sentences."
→ show_cloze_exercise (same verbs, in context)

Planner: "Good work! Time to use these in a conversation."
→ start_conversation (free production with target grammar)
```

This **drill → cloze → conversation** arc mirrors the Aula Internacional progression: mechanical practice → guided production → free production.
