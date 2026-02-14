# Adaptive Placement — Implementation Prompt

## Context

Read `PROMPT.md` for full project context, `DESIGN_IDEAS.md` section "Adaptive Placement & Multi-Dimensional Profiling" for the full design rationale. Read `BACKLOG.md` Step 7.

**The goal:** Solve the cold start problem. New users shouldn't grind through "hola means hello" if they already speak some Spanish. A placement conversation probes increasing complexity, and the post-conversation evaluation mass-unlocks concepts the user clearly already knows. Heritage speakers (grew up hearing Spanish but never studied it) get an appropriate starting point without boring tests.

**Dependencies:** Assumes all previous steps (personas, evaluation, memory, enjoyment scoring, conversation types) are implemented. This builds on top of them.

## What to build

### 1. Onboarding detection

When a user starts their first-ever flow session (no `flow_sessions` in the DB, or a special `is_onboarded` flag is false), the system enters placement mode instead of the normal card flow.

Add to `flow_db.py` or `db.py`:

```python
def is_user_onboarded() -> bool:
    """Check if the user has completed placement."""
    # Option A: Check dev_overrides for 'onboarding_complete' key
    # Option B: Check if any concept_knowledge rows exist with n_attempts > 0
    # Option C: Dedicated flag in a user_settings table
    # Go with Option A for simplicity — uses the existing dev_overrides table
```

### 2. Quick onboarding questions (pre-placement)

Before the placement conversation, ask 2-3 quick questions to set a rough starting point. This avoids the worst cold-start (someone who speaks fluently getting "¿Cómo te llamas?").

Create a `/flow/onboarding` route that renders an onboarding page:

**Question 1:** "Have you studied Spanish before?"
- Never → Start placement at A1 (tier 1)
- A little (Duolingo, a class, etc.) → Start placement at A1-A2 boundary (tier 2)
- Intermediate (can have basic conversations) → Start placement at A2 (tier 3)
- Advanced / Heritage speaker → Start placement at A2+ and skip basic concepts

**Question 2:** "Can you read this?" → Show a sentence and ask what it means
- "El gato está en la mesa" (A1)
- "Ayer fui al mercado y compré frutas" (A2)
- "Me gustaría que vinieras a la fiesta este fin de semana" (B1)

The user picks which ones they can understand. This gives a rough CEFR estimate.

**Question 3 (optional):** "What are you interested in?"
- Show the interest topics (sports, music, food, travel, etc.)
- User picks 2-3
- Seeds the interest system so the first conversation has a relevant topic

These are simple HTML forms with HTMX, nothing fancy. Store the answers and use them to configure the placement conversation.

### 3. Placement conversation

After the quick questions, start a special placement conversation. This is a conversation of type `"placement"` (new conversation type) with specific behavior:

**How it works:**
- Use a friendly, patient persona (Marta or Abuela Rosa — not Diego, who might intimidate beginners)
- Start at the complexity level suggested by the quick questions
- The persona begins with simple questions and progressively increases complexity
- If the user responds fluently, the persona ramps up: introduces past tense, asks more complex questions, uses harder vocabulary
- If the user struggles, the persona backs off and stays at the current level
- Longer than a normal conversation: 6-8 turns instead of 4

**Placement system prompt addition:**

```
CONVERSATION MODE: Placement
This is a placement conversation to assess the learner's level. Your goal is to
discover what they know, NOT to teach.

RULES:
- Start with the complexity level indicated below
- If they respond fluently and correctly, increase complexity in your next message:
  Level 1: Present tense, basic vocabulary, simple questions (¿Cómo te llamas? ¿Qué te gusta?)
  Level 2: Past tense (preterite), descriptions, opinions (¿Qué hiciste ayer? ¿Cómo es tu ciudad?)
  Level 3: Mixed tenses, conditional, subjunctive hints (¿Qué harías si...? ¿Qué te gustaría?)
  Level 4: Complex structures, idioms, abstract topics (¿Qué opinas sobre...? Si pudieras...)
- If they struggle (short answers, errors, English words), stay at the current level or drop down
- Be encouraging regardless of level — this isn't a test, it's a conversation
- Don't correct errors during placement — just note them mentally
- Ask open-ended questions that give them room to show what they know
- Naturally cover different grammar areas: tenses, ser/estar, gustar, question formation

STARTING LEVEL: {starting_level}
```

### 4. Post-placement evaluation

After the placement conversation ends, run a special evaluation that:

**a) Estimates CEFR dimensions:**
The existing evaluation already produces `estimated_cefr` with vocabulary, grammar, fluency, comprehension. Use these.

**b) Mass-unlocks concepts:**

Based on the estimated levels, mark concepts as mastered:

```python
def apply_placement_results(evaluation: ConversationEvaluation) -> dict:
    """Mass-unlock concepts based on placement conversation results.

    Returns summary of what was unlocked.
    """
    cefr = evaluation.estimated_cefr
    grammar_level = cefr.get("grammar", "A1")
    vocab_level = cefr.get("vocabulary", "A1")

    # Map CEFR to concept tiers
    # A1 = tier 1, A2 = tier 2, B1 = tier 3
    grammar_tier = {"A1": 1, "A2": 2, "B1": 3, "B2": 3}.get(grammar_level, 1)
    vocab_tier = {"A1": 1, "A2": 2, "B1": 3, "B2": 3}.get(vocab_level, 1)

    # Use the LOWER of grammar and vocab to be conservative
    # But also unlock specific concepts that were demonstrated
    safe_tier = min(grammar_tier, vocab_tier)

    # Mass-mark concepts below safe_tier as mastered (reuse skip-to-tier logic)
    unlocked_count = skip_concepts_below_tier(safe_tier)

    # Additionally, mark specific demonstrated concepts as partially known
    # even if they're above the safe tier
    for evidence in evaluation.concepts_demonstrated:
        if evidence.correct_count > 0:
            # Give them credit — set p_mastery based on accuracy
            accuracy = evidence.correct_count / evidence.usage_count
            initial_mastery = accuracy * 0.7  # conservative — don't fully master from one conversation
            set_concept_knowledge(evidence.concept_id, initial_mastery, evidence.usage_count)

    return {
        "safe_tier": safe_tier,
        "unlocked_count": unlocked_count,
        "demonstrated_concepts": [e.concept_id for e in evaluation.concepts_demonstrated],
        "estimated_cefr": cefr,
    }
```

**c) Harvest vocabulary:**
The normal `harvest_conversation_words()` runs, so all words produced during placement get tracked automatically.

**d) Store user facts:**
Any personal facts revealed during placement (name, location, interests) get stored in the memory system.

### 5. Placement summary page

After placement, show the user a summary:

```
Welcome! Based on our conversation, here's where you're starting:

Grammar: A2 — You handle present and past tense well
Vocabulary: A1-A2 — Good everyday vocabulary
Fluency: A2 — You express yourself in short sentences
Comprehension: B1 — You understand more than you produce

We've unlocked 15 concepts you already know.
Your journey starts with: [first concept name]

[Start Learning →]
```

Simple page, not fancy. The key info: what level they're at, what was unlocked, and a button to start the normal flow.

### 6. Wire into the flow

In `flow_routes.py`:

**a) Check onboarding on flow page load:**

```python
@router.get("/flow", response_class=HTMLResponse)
async def flow_page(request: Request) -> Response:
    if not is_user_onboarded():
        return RedirectResponse(url="/flow/onboarding", status_code=303)
    # ... existing flow page logic
```

**b) Onboarding route:**

```python
@router.get("/flow/onboarding", response_class=HTMLResponse)
async def onboarding_page(request: Request) -> Response:
    """Show the quick onboarding questions."""
    # Render onboarding template

@router.post("/flow/onboarding/start-placement", response_class=HTMLResponse)
async def start_placement(
    request: Request,
    experience_level: str = Form(...),  # "never", "a_little", "intermediate", "advanced"
    interests: str = Form(default=""),  # comma-separated topic IDs
) -> Response:
    """Start the placement conversation based on quick question answers."""
    # Map experience to starting level
    # Seed interest scores if interests provided
    # Start a placement conversation
    # Redirect to the placement conversation UI

@router.get("/flow/onboarding/results", response_class=HTMLResponse)
async def placement_results(
    request: Request,
    conversation_id: int = Query(...),
) -> Response:
    """Show placement results and unlock concepts."""
    # Run evaluation on the placement conversation
    # Apply placement results (mass-unlock)
    # Mark as onboarded
    # Show results page
```

**c) Add onboarding to dev tools:**

In the dev panel, add a "Re-run placement" button that:
- Clears the onboarded flag
- Optionally resets all progress
- Redirects to `/flow/onboarding`

Also add a "Skip placement" button for dev convenience.

### 7. Heritage speaker handling

For users who select "Advanced / Heritage speaker" in the quick questions:

- Start the placement conversation at level 3-4 (complex structures)
- The post-placement evaluation will likely show: high vocabulary, high fluency, low grammar awareness
- The system should then skip ALL basic vocab content, skip teach cards for concepts they demonstrate naturally
- Focus on grammar concepts, presented through conversation and MCQs
- This happens naturally through the placement unlocking — concepts they demonstrate get credit, concepts they don't stay locked

No special code needed beyond what the placement system already does. The evaluation's multi-dimensional profiling handles the uneven skill profile.

## What NOT to build yet

- No complex adaptive difficulty during placement (just pre-set levels based on quick questions)
- No retake/re-placement UI (use the dev tools "re-run placement" button)
- No visual radar chart of dimensions (just text summary)
- No B1+ content (the app only covers A1-A2 currently)

## Key design decisions

- **Conservative unlocking** — use the LOWER of grammar and vocab tiers. Better to start slightly too easy than to skip things the user doesn't actually know.
- **Specific concept credit** — concepts explicitly demonstrated in conversation get partial mastery credit even if they're above the safe tier. This handles uneven profiles.
- **Placement is a conversation, not a test** — it should feel natural, not like an exam. The persona is friendly and encouraging. No "this is a placement test" framing.
- **Quick questions set rough bounds** — they prevent the worst cases (fluent speaker getting "hola") but the real assessment happens in the conversation.
- **One placement per user** — once onboarded, you're done. Use dev tools to re-run if needed.

## Files to create

1. `templates/flow_onboarding.html` — Quick questions page
2. `templates/flow_placement_results.html` — Placement results summary page

## Files to modify

1. `src/spanish_vibes/flow_routes.py` — Add onboarding routes, placement conversation start, placement results
2. `src/spanish_vibes/flow.py` — Check onboarding status before normal flow, placement evaluation logic
3. `src/spanish_vibes/evaluation.py` — Add `apply_placement_results()` function
4. `src/spanish_vibes/db.py` — Add `is_user_onboarded()` check (via dev_overrides or new flag)
5. `src/spanish_vibes/conversation_types.py` — Add `"placement"` conversation type with ramping system prompt
6. `src/spanish_vibes/interest.py` — Seed interest scores from onboarding question answers

## Testing

- Verify onboarding redirect works on first visit
- Verify quick questions render and submit correctly
- Verify placement conversation starts at the correct complexity level
- Verify persona ramps up/down based on user responses
- Verify post-placement evaluation produces reasonable CEFR estimates
- Verify mass-unlock marks correct concepts as mastered
- Verify demonstrated concepts get partial mastery credit
- Verify onboarded flag prevents re-placement on next visit
- Verify dev tools "re-run placement" works
- Verify heritage speaker path unlocks appropriately
- Verify interests from onboarding seed the interest system
