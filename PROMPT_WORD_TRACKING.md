# Accelerate Word Tracking — Implementation Prompt

## Context

Read `PROMPT.md` for full project context, `BACKLOG.md` for task list, and `DESIGN_IDEAS.md` section "Accelerating Word Tracking (The '15 Words' Problem)" for the design rationale.

**The problem:** The words dashboard shows only ~15 tracked words. Words only enter the system through 16 seed words and English-fallback vocabulary gaps during conversations. That's way too slow. A user producing Spanish correctly in conversation gets zero credit in the word tracker.

## What to build (3 changes)

### 1. Harvest vocabulary from conversations

**Where:** `words.py` (new function), called from `flow_routes.py` `conversation_summary` endpoint.

After every conversation ends (in the `conversation_summary` endpoint, after `generate_summary()`), extract all meaningful Spanish words the user produced from their messages and track them.

**Implementation:**
- Add `harvest_conversation_words(user_messages: list[str], concept_id: str | None) -> int` to `words.py`
- Extract Spanish words from user messages, excluding stop words (a, al, con, de, del, el, en, es, la, las, lo, los, me, mi, muy, no, o, por, que, se, si, su, te, tu, un, una, y, yo, le, les, nos, pero, más, como, para, sin, ni, ya, ha, he) and short tokens (<2 chars)
- For each extracted word:
  - If it **already exists** in the `words` table: bump `times_seen` AND `times_correct` (they used it correctly in conversation — that's production evidence, stronger than MCQ recognition)
  - If it's **new**: insert into `words` table with `status='practicing'` (skip the intro card — they already produced it). Try to find the English translation from the `word_translations` cache table first; if not found, use the Spanish word as a placeholder (it'll get a real translation when they tap it or it shows up in a practice card)
- Call this from `conversation_summary` in `flow_routes.py`, right after `generate_summary()`:
  ```python
  from .words import harvest_conversation_words
  user_msgs = [m.content for m in messages if m.role == "user"]
  harvest_conversation_words(user_msgs, concept_id=concept_id or None)
  ```

### 2. Track word taps

**Where:** `db.py` (new table), `words.py` (new function), `flow_routes.py` (modify translate endpoint), `flow_conversation.html` (pass conversation_id).

When a user taps a word for translation during a conversation, record it. This is a signal: "I don't know this word" or "I'm curious about this word."

**Implementation:**

a) **New table** in `db.py` `_create_word_tables()`:
```sql
CREATE TABLE IF NOT EXISTS word_taps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    spanish_word TEXT NOT NULL,
    english_translation TEXT,
    conversation_id INTEGER,
    source TEXT NOT NULL DEFAULT 'conversation',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_word_taps_spanish ON word_taps(spanish_word);
```

b) **New function** `record_word_tap(spanish, english=None, conversation_id=None, source="conversation")` in `words.py`:
- Record every tap in `word_taps` (full history, NOT upserted — we want to see repeated lookups)
- Also ensure the word exists in `words` table: if new and we have the English translation, insert as `status='unseen'` (they looked it up because they DON'T know it). If it already exists, bump `times_seen`.

c) **Modify** the `/flow/translate-word` endpoint in `flow_routes.py`:
- Add optional `conversation_id: int | None = Query(default=None)` parameter
- After translating, call `record_word_tap(word, english=result["translation"], conversation_id=conversation_id)`

d) **Pass conversation_id** in the JS fetch URL in `templates/partials/flow_conversation.html`:
- The template already has `{{ conversation_id }}` available
- In `requestTranslation()`, append `&conversation_id=...` to the fetch URL

### 3. Smart word lifecycle (skip intro for conversation words)

This is already handled by #1 above — conversation-produced words enter as 'practicing' not 'unseen'. But also:

- **Tapped words** enter as 'unseen' (they need to be taught)
- **Conversation-produced words** enter as 'practicing' (they already demonstrated knowledge)
- **Existing words that appear in conversation** get `times_correct` bumped (stronger evidence of mastery)

No changes needed to the intro card pipeline itself — it already only picks 'unseen' words for intro. The effect is: conversation words bypass intro entirely, while tapped words still go through the intro→practice→known flow.

## What NOT to build yet

- Don't change the intro card selection logic (that's a separate task about beginner vs intermediate priorities)
- Don't add topic_id tagging to words yet (that's part of interest-driven vocab, a bigger change)
- Don't change the word practice card logic
- Don't change the words dashboard

## Testing

- Verify `_extract_spanish_words` correctly filters stop words and short tokens
- Verify `harvest_conversation_words` inserts new words as 'practicing' and bumps existing words
- Verify `record_word_tap` records taps and creates/updates words table entries
- Verify the translate endpoint now calls `record_word_tap`
- Run existing tests to ensure nothing breaks

## Current state of the code

**`words.py` already has the new functions** — `record_word_tap()`, `harvest_conversation_words()`, `_extract_spanish_words()`, `_lookup_cached_english()`, `get_tap_counts()`, and the `_STOP_WORDS` set. Review them and adjust if needed, but don't rewrite from scratch.

**Still needs to be done:**
1. `src/spanish_vibes/db.py` — Add `word_taps` table in `_create_word_tables()`
2. `src/spanish_vibes/flow_routes.py` — Call `harvest_conversation_words` from `conversation_summary` endpoint, modify `/flow/translate-word` endpoint to accept `conversation_id` param and call `record_word_tap`
3. `templates/partials/flow_conversation.html` — Pass `conversation_id` in the JS translate fetch URL
