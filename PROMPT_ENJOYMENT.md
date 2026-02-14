# Enjoyment Scoring + Persona Rotation — Implementation Prompt

## Context

Read `PROMPT.md` for full project context, `DESIGN_IDEAS.md` section "Conversation Enjoyment Score (TikTok-style Persona Ranking)" for the full design rationale. Read `BACKLOG.md` Step 5.

**The goal:** Replace random persona selection with a TikTok-style algorithm that learns which persona+topic combos the user enjoys most. After each conversation, compute an enjoyment score from behavioral signals. Over time, the system shows more of what engages and less of what doesn't — without ever asking the user directly.

**Dependencies:** Assumes personas (Steps 1+2), evaluation (Step 3), and memory (Step 4) are implemented. The evaluation module already extracts `engagement_quality` — this step computes a richer score and uses it for selection.

## What to build

### 1. New `persona_engagement` table

Add to `db.py`:

```sql
CREATE TABLE IF NOT EXISTS persona_engagement (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    persona_id TEXT NOT NULL,
    topic_id INTEGER,
    conversation_count INTEGER NOT NULL DEFAULT 0,
    avg_enjoyment_score REAL NOT NULL DEFAULT 0.5,
    avg_message_length REAL NOT NULL DEFAULT 0.0,
    avg_turns REAL NOT NULL DEFAULT 0.0,
    early_exit_rate REAL NOT NULL DEFAULT 0.0,
    last_conversation_at TEXT,
    UNIQUE(persona_id, topic_id)
);
CREATE INDEX IF NOT EXISTS idx_persona_engagement_persona ON persona_engagement(persona_id);
```

`topic_id` is nullable — a NULL topic_id row tracks the persona's overall engagement regardless of topic. This lets us score both "how much do I like Diego?" (persona-level) and "how much do I like Diego talking about football?" (persona+topic combo).

### 2. Enjoyment score computation

Add to `evaluation.py` (or a new `engagement.py` if you prefer — either works):

```python
def compute_enjoyment_score(
    messages: list[ConversationMessage],
    max_turns: int = 4,
    engagement_quality_from_llm: float = 0.5,
) -> float:
    """Compute enjoyment score from behavioral signals.

    Returns 0.0-1.0 score.
    """
```

**Signals and weights:**

```
enjoyment_score = weighted sum of:
  - message_length_norm:  0.35  (avg words per user message, normalized 0-1)
  - completion_ratio:     0.25  (user_turns / max_turns)
  - no_early_exit:        0.20  (1.0 if completed all turns, 0.0 if exited early)
  - response_time_score:  0.10  (not available yet — use 0.5 default for now)
  - engagement_quality:   0.10  (from LLM evaluation, already extracted)
```

**Message length normalization:**
- Count words per user message, take the average
- Normalize: 0 words = 0.0, 1-3 words = 0.2, 4-7 words = 0.5, 8-12 words = 0.7, 13+ words = 1.0
- This is rough but captures the difference between "sí" and actual sentences

**Completion ratio:**
- `user_turn_count / max_turns`
- If they sent 4 messages out of 4 max: 1.0
- If they hit Done after 2: 0.5

**Early exit detection:**
- Check if the conversation was completed naturally (hit max_turns) or if the user tapped Done early
- The `flow_conversations` table has `completed` flag and turn count data
- Natural completion = 1.0, early exit = 0.0

**Response time:**
- Not currently tracked in message timestamps (messages have timestamps but they're set server-side during the request, not when the user actually typed)
- Default to 0.5 for now. TODO: track actual client-side response time in a future iteration.

### 3. Update persona_engagement after each conversation

Add a function:

```python
def update_persona_engagement(
    persona_id: str,
    topic_id: int | None,
    enjoyment_score: float,
    avg_message_length: float,
    turn_count: int,
    was_early_exit: bool,
) -> None:
    """Update the running averages for a persona+topic combo.

    Uses incremental averaging: new_avg = old_avg + (new_value - old_avg) / count
    Also updates the persona-level row (topic_id=NULL).
    """
```

This should update TWO rows:
1. The specific `(persona_id, topic_id)` combo
2. The overall `(persona_id, NULL)` row — persona-level score regardless of topic

Use `INSERT ... ON CONFLICT ... DO UPDATE` for upsert.

### 4. Wire into the conversation summary flow

In `flow_routes.py` `conversation_summary` endpoint, after the evaluation call:

```python
from .evaluation import compute_enjoyment_score  # or engagement.py

# Compute enjoyment score
user_msgs = [m for m in messages if m.role == "user"]
enjoyment = compute_enjoyment_score(
    messages=messages,
    max_turns=card.max_turns,
    engagement_quality_from_llm=evaluation.engagement_quality if evaluation else 0.5,
)

# Compute avg message length for tracking
avg_msg_len = sum(len(m.content.split()) for m in user_msgs) / len(user_msgs) if user_msgs else 0.0

# Detect early exit
was_early_exit = card.user_turn_count < card.max_turns

# Get topic_id if available (from interest tracking)
topic_id = None  # TODO: wire in when conversations track topic_id

# Update engagement
update_persona_engagement(
    persona_id=persona.id,
    topic_id=topic_id,
    enjoyment_score=enjoyment,
    avg_message_length=avg_msg_len,
    turn_count=card.turn_count,
    was_early_exit=was_early_exit,
)
```

### 5. Replace random persona selection with weighted selection

Modify `personas.py` `select_persona()`:

```python
def select_persona(exclude_id: str | None = None) -> Persona:
    """Select a persona weighted by engagement scores + novelty bonus.

    Algorithm:
    1. Load all personas
    2. For each, get their persona-level engagement score (topic_id=NULL row)
    3. Compute selection score:
       score = engagement_affinity * 0.6 + novelty_bonus * 0.3 + random_explore * 0.1
    4. Pick using weighted random selection

    Novelty bonus:
    - Higher if this persona hasn't been used recently
    - Prevents the system from always picking the same persona
    - New personas (0 conversations) get a bonus to ensure fair trial

    Exploration:
    - 10% random component ensures all personas get occasional play
    - Prevents complete lock-in to one persona
    """
```

**Engagement affinity:**
- Load from `persona_engagement` table where `topic_id IS NULL`
- Use `avg_enjoyment_score` (0.0-1.0)
- New personas (no rows) default to 0.5 (neutral — benefit of the doubt)

**Novelty bonus:**
- Based on days since `last_conversation_at`
- 0 days ago = 0.0 (just used), 1 day = 0.3, 3+ days = 0.7, never used = 1.0
- Scale: `min(1.0, days_since_last / 5.0)` or similar

**Exploration component:**
- Pure random 0.0-1.0
- Small weight (0.1) but ensures no persona is completely starved

**Selection method:**
- Compute score for each persona (excluding `exclude_id`)
- Use weighted random choice (not argmax — we want probabilistic, not deterministic)
- `random.choices(personas, weights=scores, k=1)[0]`

### 6. Engagement dashboard (optional but nice)

Add engagement data to an existing page (maybe the flow stats page or a new `/flow/engagement` route):

- Show each persona with their avg enjoyment score and conversation count
- Simple table or cards, nothing fancy
- Useful for debugging and for the user to see "your Spanish friends"

This is optional — skip if time is tight.

## What NOT to build yet

- No topic-level engagement tracking in persona selection (we don't track topic_id on conversations yet — just use persona-level scores)
- No response time tracking (requires client-side changes)
- No engagement decay over time (half-life approach from the design doc — add later)
- No conversation types affecting selection (Step 6)

## Key design decisions

- **Incremental averaging** — don't recompute from all conversations. Update running averages after each conversation. Simpler and faster.
- **Neutral start** — new personas start at 0.5, not 0.0. They get a fair trial before the system judges them.
- **Probabilistic, not deterministic** — weighted random, not "always pick the highest score." This is key to the TikTok model — explore while exploiting.
- **Exclude last persona** — already implemented. Don't show the same persona twice in a row within a session.
- **Persona-level first** — track per-persona scores before per-persona+topic. The combo tracking exists in the table schema but persona selection only uses persona-level for now.
- **Fail gracefully** — if engagement loading fails, fall back to random selection (existing behavior).

## Files to create

None — all code goes in existing modules.

## Files to modify

1. `src/spanish_vibes/db.py` — Add `persona_engagement` table
2. `src/spanish_vibes/evaluation.py` — Add `compute_enjoyment_score()` and `update_persona_engagement()`
3. `src/spanish_vibes/personas.py` — Replace random `select_persona()` with weighted selection
4. `src/spanish_vibes/flow_routes.py` — Wire enjoyment computation + engagement update into `conversation_summary`

## Testing

- Verify enjoyment score computation produces sensible scores for different conversation patterns:
  - Long messages + full completion = high score (~0.8+)
  - Short "sí/no" messages + early exit = low score (~0.2)
  - Mixed = middle (~0.5)
- Verify persona_engagement table updates correctly after conversations
- Verify both persona-level and persona+topic rows are updated
- Verify weighted selection favors high-engagement personas over low ones (run 100 selections, check distribution)
- Verify new personas (no data) still get selected (neutral start + novelty bonus)
- Verify excluded persona is never selected
- Verify fallback to random if engagement table is empty
