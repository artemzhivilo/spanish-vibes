# Implement: Adaptive User Level & Difficulty System

## Overview

The current difficulty system is static — each concept has a fixed `difficulty_level` (1-3) and the player "level" is purely XP-based (decorative). Nothing adapts to how the user is actually performing. This prompt adds a **computed user level** derived from BKT mastery data, then wires it into MCQ selection and conversation difficulty.

## Current State (what exists)

- **Concept `difficulty_level`**: 1-3 per concept in concepts.yaml. Used for unlock ordering and conversation CEFR mapping.
- **MCQ `difficulty`**: 1-3 per MCQ card, set by AI during generation. But `_get_mcq_for_concept()` just grabs the least-used MCQ — it ignores difficulty entirely.
- **Player level**: XP-based via `level_from_xp()` in srs.py. Purely cosmetic.
- **`_DIFFICULTY_TO_CEFR`**: `{1: "A1", 2: "A1-A2", 3: "A2"}` in conversation.py. Used in AI prompts.
- **`SCAFFOLDING_RULES`**: 3 tiers of conversation support. Good but tied to concept difficulty, not user ability.
- **Post-conversation evaluation** already returns `estimated_cefr` per conversation (in evaluation.py) but this data is never used.

## What to Build (4 changes)

### Change 1: Compute User Level from BKT Data

Create a function `get_user_level()` in `flow.py` (or a new `user_level.py` module) that computes a global difficulty level from existing BKT mastery data.

```python
def get_user_level(
    knowledge: dict[str, ConceptKnowledge] | None = None,
    concepts: dict[str, Concept] | None = None,
) -> dict:
    """Compute global user level from BKT mastery data.

    Returns dict with:
        level: int (1-3, maps to concept tiers)
        cefr: str ("A1", "A1-A2", "A2", "A2-B1")
        tier_mastery: dict[int, float] (% mastered per tier, e.g. {1: 0.85, 2: 0.40, 3: 0.0})
        session_difficulty: int (1-3, the difficulty to use for content selection)
        total_mastered: int
        total_concepts: int
    """
```

**Logic:**
1. Group all concepts by their `difficulty_level` (tier 1, 2, 3)
2. For each tier, calculate what fraction of concepts are mastered (p_mastery >= 0.90, n_attempts >= 5)
3. Determine user level based on tier mastery:
   - If tier 1 mastery < 50%: level=1, cefr="A1"
   - If tier 1 mastery >= 50% but < 80%: level=1, cefr="A1" (still consolidating basics)
   - If tier 1 mastery >= 80% and tier 2 mastery < 50%: level=2, cefr="A1-A2"
   - If tier 2 mastery >= 50% but < 80%: level=2, cefr="A2"
   - If tier 2 mastery >= 80%: level=3, cefr="A2-B1"
4. `session_difficulty` = the user's level (1-3), used for MCQ and conversation difficulty selection

**Cache this** — it only needs to recalculate when mastery changes, not on every card. A simple module-level cache that resets when `update_concept_knowledge()` is called is fine.

### Change 2: Wire User Level into MCQ Selection

Currently `_get_mcq_for_concept()` in flow.py grabs the least-used MCQ regardless of difficulty. Change it to **prefer MCQs matched to the user's level**.

In `flow_db.py`, modify `get_cached_mcqs()` (or add a new function) to accept a `preferred_difficulty` parameter:

```python
def get_cached_mcqs(concept_id: str, limit: int = 1, preferred_difficulty: int | None = None) -> list[MCQCard]:
    """Get least-used MCQ cards for a concept, preferring matching difficulty."""
```

**Selection logic:**
1. First, try to find MCQs where `difficulty == preferred_difficulty`, ordered by `times_used ASC`
2. If none available at that difficulty, fall back to any difficulty (current behavior)
3. This is a soft preference, not a hard filter — we never want to show no cards

Then in `_get_mcq_for_concept()` in flow.py, pass the user level:

```python
def _get_mcq_for_concept(concept_id: str) -> MCQCard | None:
    user_level = get_user_level()
    mcqs = get_cached_mcqs(concept_id, limit=1, preferred_difficulty=user_level["session_difficulty"])
    return mcqs[0] if mcqs else None
```

### Change 3: Wire User Level into Conversations

The conversation system currently derives CEFR from concept difficulty. Change it to use the user's computed level instead, since a user might be studying a tier-1 concept but actually be at A2 level.

**In `_start_chat_conversation_card()` (flow_routes.py ~line 1834):**

Replace the static difficulty with the user level:

```python
from .flow import get_user_level  # or wherever it lives

user_level_info = get_user_level()
# Use user's global level instead of concept's static difficulty
effective_difficulty = user_level_info["session_difficulty"]
```

Pass `effective_difficulty` instead of `card_context.difficulty` to the conversation engine functions.

**In `_DIFFICULTY_TO_CEFR` (conversation.py line 379):**

Expand the mapping to handle the new levels:

```python
_DIFFICULTY_TO_CEFR = {1: "A1", 2: "A2", 3: "A2-B1"}
```

**In `SCAFFOLDING_RULES` (conversation.py line 43):**

The existing 3 tiers are good. Just make sure they're keyed to 1, 2, 3 which they already are.

**In the conversation AI prompts** (generate_opener, generate_response, etc.):

The CEFR level is already injected via the `cefr` variable. Since we're changing what feeds into `difficulty`, the prompts will automatically use the user's actual level. No prompt text changes needed.

### Change 4: Show User Level in the UI

**In the flow page header (templates/flow.html ~line 7):**

Add a level badge that shows the computed CEFR level, not just the XP level. Something like:

```html
<span class="rounded-full bg-amber-500/15 px-3 py-1 text-xs font-bold text-amber-300">
  {{ user_cefr }}
</span>
```

**In `flow_page()` (flow_routes.py ~line 90):**

Add to context:

```python
user_level_info = get_user_level(knowledge, concepts)
context["user_cefr"] = user_level_info["cefr"]
context["user_level"] = user_level_info["level"]
context["tier_mastery"] = user_level_info["tier_mastery"]
```

**In the dev panel state (`_build_dev_state_payload` in flow_routes.py):**

Add user level info to the dev state so it's visible for debugging:

```python
payload["user_level"] = get_user_level()
```

## Files to Modify

1. **`src/spanish_vibes/flow.py`** — Add `get_user_level()` function and update `_get_mcq_for_concept()` to pass preferred difficulty
2. **`src/spanish_vibes/flow_db.py`** — Update `get_cached_mcqs()` to accept `preferred_difficulty` parameter
3. **`src/spanish_vibes/flow_routes.py`** — Pass user level info to templates and conversation engine
4. **`src/spanish_vibes/conversation.py`** — Update `_DIFFICULTY_TO_CEFR` mapping
5. **`templates/flow.html`** — Display CEFR badge in header

## What This Does NOT Do (future work)

- **No Elo ratings for questions** — needs multi-user data to calibrate, premature for now
- **No in-session difficulty ramping** — e.g. "user got 5 right in a row, serve a harder card". Good idea but adds complexity. Can be a follow-up.
- **No per-skill-category tracking** — e.g. separating "grammar mastery" from "vocab mastery". BKT already tracks per-concept; grouping concepts into categories is a separate project.
- **No conversation evaluation feedback loop** — the `estimated_cefr` from evaluation.py could feed back into the user level calculation. Worth doing later once there's enough conversation data.

## How to Verify

1. Check a user with mostly tier-1 mastery: `get_user_level()` should return level=1, cefr="A1"
2. Use "Skip Level" to jump to tier 2, master some concepts: level should update to 2, cefr="A1-A2" or "A2"
3. MCQ selection: if user is level 2, verify that difficulty=2 MCQs are served preferentially (check via dev panel)
4. Conversations: start a conversation and check the AI prompt includes the correct CEFR level (check server logs)
5. Flow page header: verify the CEFR badge shows and updates
