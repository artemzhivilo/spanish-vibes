# Fix: Interest Tracking — Wire Up the Signals

## The Problem

The interest tracking system is fully built (21 topics, EMA scoring, time decay, top-N retrieval) but completely disconnected. Every CardSignal has `topic_id=None` (hardcoded on line ~297 of flow_routes.py), so the tracker's early-exit path fires on 100% of signals. After 230+ cards answered, there are zero interest scores recorded. Conversations don't create signals at all.

## Current State

- `interest_topics` table: 21 topics seeded ✓
- `user_interest_scores` table: **0 records** (empty)
- `card_signals` table: 230 records, **ALL with topic_id=NULL**
- `InterestTracker.update_from_card_signal()`: Works correctly but never receives a topic_id
- `InterestTracker.get_top_interests()`: Called on every card selection, always returns empty list
- Conversations have a `topic` field but never feed signals back

## Design Principle

**Conversations are the signal source. MCQs are the signal consumer.**

MCQ answers should NOT generate interest signals — the user didn't choose to practice `food_vocab`, the engine assigned it. Getting a food question right doesn't mean you're interested in food.

Conversations are where genuine interest signals live: the user engages voluntarily, chats for multiple turns, shows enthusiasm or disinterest through message length and engagement. Conversation topics and engagement quality are the real preference data.

The flow is: **Conversations → interest signals → scores update → scores influence future conversation topic selection AND MCQ theming**

## The Fix (3 changes)

### Change 1: Topic Matching for Conversations

Add a function to `interest.py` that matches a conversation's topic string to an interest topic in the database:

```python
def get_topic_id_for_conversation(topic: str, concept_id: str | None = None) -> int | None:
    """Match a conversation topic string to an interest topic_id.

    Tries matching the topic string against interest_topics names.
    e.g. topic="football" → matches "Football" topic
    e.g. topic="cooking" → matches "Food & Cooking" topic
    Returns the topic_id or None if no match.
    """
    # 1. Lowercase the topic string
    # 2. Query all interest_topics
    # 3. Check if topic is a substring of any interest_topics.name (lowercased), or vice versa
    # 4. Return the best match's id, or None
```

Keep the matching simple — lowercase substring check. Conversation topics are typically things like "football", "cooking", "travel", "music" which map cleanly to the seeded interest topics. If there's no match, return None and skip scoring — no harm done.

Also add a concept-to-topic mapping as a fallback, for when the conversation topic string doesn't match but the concept does:

```python
CONCEPT_TOPIC_MAP: dict[str, str] = {
    "food_vocab": "food-cooking",
    "ordering_food": "food-cooking",
    "animals_vocab": "nature-animals",
    "clothing_vocab": "fashion",
    "body_parts": "health",
    "professions": "business",
    "family_vocab": "relationships",
    "hobbies_free_time": "gaming",
    "weather_seasons": "nature-animals",
    "places_in_town": "travel",
    "travel_transport": "travel",
    "shopping": "fashion",
    "health_doctor": "health",
    "my_city": "travel",
    "describing_people": "relationships",
}
```

The function should: try topic string match first → fall back to concept mapping → return None if neither works.

### Change 2: Create Interest Signals from Conversations

Conversations are the PRIMARY signal source. When a conversation completes (summary is generated), create an interest signal.

In the conversation summary endpoint in `flow_routes.py`, after the evaluation is processed, add:

```python
# Record interest signal for the conversation
from .interest import InterestTracker, get_topic_id_for_conversation

conv_topic_id = get_topic_id_for_conversation(topic, concept_id)
if conv_topic_id:
    from .models import CardSignal
    conv_signal = CardSignal(
        topic_id=conv_topic_id,
        was_correct=True,  # completed conversation = positive engagement
        dwell_time_ms=None,
        response_time_ms=None,
        card_id=None,
        session_id=session_id,
        concept_id=concept_id,
        card_type="conversation",
    )
    InterestTracker().update_from_card_signal(conv_signal)
```

**Bonus — weight by engagement quality:** If the enjoyment/engagement scoring is available from the evaluation, use it to modulate the signal strength. A conversation where the user sent long messages and stayed engaged is a stronger interest signal than one where they typed one word and hit "Done". This can be done by setting `was_correct=True` for high engagement and `was_correct=False` for low engagement (or early exits), since the tracker's engagement calculation weights correctness at 0.40.

### Change 3: Remove MCQ Interest Signals

In `flow_routes.py` in the `flow_answer()` endpoint (~line 295), the existing CardSignal creation can stay for tracking purposes (dwell time, response time, accuracy — useful data), but **keep `topic_id=None`** so it doesn't feed into interest scoring. MCQ answers are assigned, not chosen, so they shouldn't influence interest preferences.

Alternatively, if you want to simplify, you could remove the `InterestTracker().update_from_card_signal(signal)` call entirely from the MCQ answer path and only call it from the conversation path. The raw signal still gets recorded to `card_signals` table regardless (the tracker records it before the early exit). But keeping the call is fine too — with `topic_id=None` it records the signal and returns 0.0.

**No changes needed to the MCQ signal creation code.** Leave `topic_id=None` as-is. The MCQ path just records raw signal data without updating interest scores.

## Files to Modify

1. **`src/spanish_vibes/interest.py`** — Add `CONCEPT_TOPIC_MAP`, `get_topic_id_for_conversation()`
2. **`src/spanish_vibes/flow_routes.py`** — One change:
   - Conversation summary endpoint: Add interest signal creation after evaluation

## What This Does NOT Do

- **No MCQ interest signals** — by design. MCQs consume interests (via theming), they don't produce them.
- **No word tap → interest mapping** — could be a future signal source but adds complexity.
- **No retroactive scoring** — existing signals stay untagged.
- **No MCQ topic theming yet** — MCQs could be generated themed to top interests. That's a separate enhancement on the consumption side. This prompt fixes the signal input side.

## How to Verify

1. Complete a conversation about cooking → check `card_signals` table, last row should have `topic_id` pointing to "Food & Cooking" and `card_type="conversation"`
2. Check `user_interest_scores` → should now have a row for the matched topic with a non-zero score
3. Complete several conversations on different topics → multiple interest scores should appear
4. On next card selection, `get_top_interests(5)` should return actual topics instead of empty list
5. Start a new conversation → topic should be influenced by interest scores (check conversation's `topic` field)
6. Answer an MCQ → `card_signals` should have a row with `topic_id=NULL` (confirming MCQs don't feed interest scores)
