# Memory System — Implementation Prompt

## Context

Read `PROMPT.md` for full project context, `DESIGN_IDEAS.md` sections "Persona System ('Souls')" (memory system subsection) and "Technical Architecture" (DB schemas, evaluation flow). Read `BACKLOG.md` Step 4.

**The goal:** Conversations should feel personal and connected — not like starting from scratch every time. After talking to Diego about football, the next Diego conversation should reference that. After telling Marta you have a dog named Max, every persona should know about Max.

**Dependencies:** Assumes personas (Steps 1+2) and evaluation (Step 3) are already implemented. The evaluation module already extracts `user_facts` and `persona_observations` — they're currently just printed to the console. This step persists them and injects them back into future conversations.

## What to build

### 1. Two new DB tables

Add to `db.py` in a new `_create_memory_tables()` function, called from the main schema setup.

**`persona_memories`** — what each persona remembers from past conversations with this user:

```sql
CREATE TABLE IF NOT EXISTS persona_memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    persona_id TEXT NOT NULL,
    memory_text TEXT NOT NULL,
    conversation_id INTEGER,
    importance_score REAL NOT NULL DEFAULT 0.5,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_persona_memories_persona ON persona_memories(persona_id);
```

**`user_profile`** — facts about the user, shared across all personas:

```sql
CREATE TABLE IF NOT EXISTS user_profile (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL UNIQUE,
    value TEXT NOT NULL,
    source_conversation_id INTEGER,
    confidence REAL NOT NULL DEFAULT 0.5,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

### 2. New `memory.py` module

Create `src/spanish_vibes/memory.py` with these functions:

**Storing memories (called after evaluation):**

```python
def store_persona_memories(
    persona_id: str,
    observations: list[str],
    conversation_id: int | None = None,
) -> int:
    """Store persona-specific observations from a conversation.

    Each observation becomes a row in persona_memories.
    Cap at ~20 memories per persona — when over the limit, delete the
    oldest with the lowest importance_score.
    Returns count of memories stored.
    """
```

```python
def store_user_facts(
    facts: list[str],
    conversation_id: int | None = None,
) -> int:
    """Store user facts discovered during a conversation.

    Each fact is a natural-language string like "User has a dog named Max".
    Use the fact text as the key (or a normalized version).
    UPSERT — if a similar fact exists, update it with higher confidence.
    Returns count of new facts stored.
    """
```

**Retrieving memories (called before each conversation):**

```python
def get_persona_memories(persona_id: str, limit: int = 10) -> list[str]:
    """Get recent memories for a persona, ordered by importance then recency.
    Returns list of memory_text strings ready for prompt injection.
    """
```

```python
def get_user_profile(limit: int = 10) -> list[str]:
    """Get user profile facts, ordered by confidence then recency.
    Returns list of "key: value" or natural-language strings.
    """
```

**Memory pruning:**

```python
def prune_persona_memories(persona_id: str, max_memories: int = 20) -> int:
    """Delete oldest/least-important memories when over the cap.
    Keep the most important and most recent.
    Returns count of memories pruned.
    """
```

### 3. Memory injection into persona prompts

Modify `personas.py` `get_persona_prompt()` to accept and inject memories:

```python
def get_persona_prompt(
    persona: Persona | None,
    persona_memories: list[str] | None = None,
    user_facts: list[str] | None = None,
) -> str:
    """Build the full system prompt with memory injection."""
    base_prompt = persona.system_prompt if persona else MARTA_PERSONA

    sections = [base_prompt]

    if persona_memories:
        memory_block = "\n".join(f"- {m}" for m in persona_memories)
        sections.append(
            f"\nTHINGS YOU REMEMBER FROM PAST CONVERSATIONS:\n{memory_block}\n"
            "Use these naturally in conversation — don't force them, but reference "
            "them when relevant. Don't say 'I remember you said...' every time."
        )

    if user_facts:
        facts_block = "\n".join(f"- {f}" for f in user_facts)
        sections.append(
            f"\nWHAT YOU KNOW ABOUT THE LEARNER:\n{facts_block}\n"
            "All personas know these facts. Use them naturally to make "
            "conversation feel personal."
        )

    return "\n\n".join(sections)
```

### 4. Wire storage into the evaluation flow

In `flow_routes.py` `conversation_summary` endpoint, replace the current `print()` logging with actual persistence:

```python
# Replace:
if evaluation.user_facts:
    print(f"[eval] User facts discovered: {evaluation.user_facts}")
if evaluation.persona_observations:
    print(f"[eval] Persona observations: {evaluation.persona_observations}")

# With:
from .memory import store_persona_memories, store_user_facts

if evaluation.persona_observations:
    store_persona_memories(
        persona_id=persona.id,
        observations=evaluation.persona_observations,
        conversation_id=conversation_id,
    )
if evaluation.user_facts:
    store_user_facts(
        facts=evaluation.user_facts,
        conversation_id=conversation_id,
    )
```

### 5. Wire retrieval into conversation start

In `flow_routes.py` wherever `get_persona_prompt()` is called before a conversation (both `conversation_start` and `conversation_reply` endpoints):

```python
from .memory import get_persona_memories, get_user_profile

memories = get_persona_memories(persona.id)
user_facts = get_user_profile()
persona_prompt = get_persona_prompt(persona, persona_memories=memories, user_facts=user_facts)
```

This happens in three places:
1. `conversation_start` — when generating the opener
2. `conversation_reply` — when responding to user messages (the persona should maintain memory awareness throughout the conversation, not just at the start)
3. `conversation_summary` — when generating the summary (less critical but keeps consistency)

### 6. Importance scoring for persona memories

When storing persona memories, assign importance based on content:

- Mentions of user's personal details (name, family, pets, location): **0.8**
- Learning observations (struggles, strengths): **0.7**
- Topic preferences and reactions: **0.6**
- Generic conversation notes: **0.4**

For the initial implementation, a simple keyword-based heuristic is fine:

```python
def _score_importance(memory_text: str) -> float:
    """Score memory importance based on content."""
    text = memory_text.lower()
    if any(w in text for w in ["name", "nombre", "family", "familia", "pet", "mascota", "dog", "perro", "cat", "gato", "lives in", "vive en"]):
        return 0.8
    if any(w in text for w in ["struggled", "difficulty", "error", "mistake", "strength", "good at", "strong"]):
        return 0.7
    if any(w in text for w in ["likes", "loves", "enjoys", "interested", "favorite", "prefers"]):
        return 0.6
    return 0.4
```

### 7. User fact deduplication

User facts can be redundant across conversations ("User has a dog" vs "User mentioned having a dog named Max"). The `store_user_facts` function should:

- Normalize facts to a key (lowercase, simplified)
- On conflict, keep the more detailed/confident version
- Don't store trivially obvious facts ("User is learning Spanish")

A simple approach: use the first ~50 chars of the fact as the key, UPSERT on conflict. Not perfect, but good enough to start. The LLM evaluation prompt could also be tweaked to produce more structured facts (e.g., "pet: dog named Max" instead of "User mentioned they have a dog named Max").

## What NOT to build yet

- No enjoyment scoring (Step 5)
- No persona engagement tracking (Step 5)
- No weighted persona selection (Step 5)
- No memory conflict resolution (open question — handle manually for now)
- No memory editing UI (users can't see or manage memories yet)

## Key design decisions

- **20 memory cap per persona** — keeps prompt size manageable. When over, prune lowest importance + oldest.
- **User facts are shared** — every persona knows the same facts. This means Diego knows about your dog even if you only told Marta. That's intentional: it simulates a friend group that talks about you.
- **Memories are injected as system prompt additions** — not as separate messages. This keeps the conversation history clean.
- **Don't force callbacks** — the prompt tells the persona to use memories "naturally, when relevant." Forcing every conversation to start with "How's Max?" gets annoying fast.
- **Fail gracefully** — if memory loading fails, the conversation still works with the base persona prompt. Memories are additive.

## Files to create

1. `src/spanish_vibes/memory.py` — Memory storage, retrieval, pruning, importance scoring

## Files to modify

1. `src/spanish_vibes/db.py` — Add `persona_memories` and `user_profile` tables
2. `src/spanish_vibes/personas.py` — Modify `get_persona_prompt()` to accept and inject memories
3. `src/spanish_vibes/flow_routes.py` — Wire memory storage (after evaluation) and retrieval (before conversation) into the three conversation endpoints

## Testing

- Verify memories persist to DB after a conversation with evaluation
- Verify memories load correctly for a persona
- Verify user facts are shared across personas (store via Marta, retrieve for Diego)
- Verify memory pruning works (store 25 memories, verify only 20 remain, lowest importance pruned)
- Verify memory injection appears in the system prompt
- Verify conversation still works if memory tables are empty
- Verify conversation still works if memory loading fails (graceful fallback)
