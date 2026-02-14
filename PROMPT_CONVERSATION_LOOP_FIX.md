# Fix: Conversation Infinite Loop Bug

## The Problem

When `cards_answered` lands on a multiple of 5 (the conversation frequency), `select_next_card()` triggers a conversation. But `cards_answered` is only incremented when the conversation **summary is generated** (in the summary endpoint). If the user abandons, skips, or fails to complete a conversation, `cards_answered` stays stuck at a multiple of 5 — and **every subsequent call to `select_next_card()` triggers another conversation**, creating an infinite loop.

This is happening right now: session 5 has `cards_answered=15`, three abandoned conversations (score=None, completed=0), and the user is stuck seeing conversation attempts every time they try to get a new card.

## Root Cause

In `flow_routes.py` ~line 1236, `cards_answered` is only incremented inside the conversation summary endpoint, gated by `if score_was_none`. If the user never reaches the summary (abandons the convo, browser refreshes, API error, etc.), the counter never moves.

Meanwhile in `flow.py` ~line 178-183, the conversation trigger check is:
```python
if (
    cards_so_far > 0
    and cards_so_far % conversation_every_n == 0
    and is_experienced
    and ai_available()
):
```

Since `cards_so_far` never changes, this fires every time.

## The Fix (2 changes)

### Change 1: Increment `cards_answered` when conversation STARTS

In `flow_routes.py`, in the `_start_chat_conversation_card()` function, add an increment right after the conversation is inserted into the DB (~after line 1880):

```python
# After conn.commit() and getting conversation_id:
session = get_session(session_id)
if session:
    update_session(session_id, cards_answered=session.cards_answered + 1)
```

This ensures that even if the conversation is abandoned, `cards_answered` moves past the trigger point.

### Change 2: Remove the duplicate increment from summary endpoint

In the conversation summary endpoint (~line 1233-1236), remove or comment out:

```python
# REMOVE THIS BLOCK — cards_answered is now incremented at conversation start
if score_was_none:
    session = get_session(session_id)
    if session:
        update_session(session_id, cards_answered=session.cards_answered + 1)
```

This prevents double-counting (once at start, once at summary).

### Change 3: Also increment for story comprehension cards

Check `_render_story_comprehension_card()` for the same pattern. If story comprehension cards also go through a summary flow that increments `cards_answered`, move that increment to the start function too. If story comprehension cards don't increment at all, add the same increment pattern there.

## Files to modify

- `src/spanish_vibes/flow_routes.py`:
  - `_start_chat_conversation_card()` — add `update_session(session_id, cards_answered=...)` after DB insert
  - Conversation summary endpoint — remove the `cards_answered` increment
  - `_render_story_comprehension_card()` — check/fix same pattern

## How to verify

After the fix:
1. Start a new session
2. Answer 5 MCQs (cards_answered reaches 5)
3. A conversation should appear
4. Click "Done" immediately without chatting, or just skip it
5. The next card should be an MCQ (not another conversation)
6. `cards_answered` should be 6 (not stuck at 5)
