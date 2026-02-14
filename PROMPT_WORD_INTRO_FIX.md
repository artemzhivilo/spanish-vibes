# PROMPT: Fix Word Intro Card Frequency & Quality

## Problem

Word intro cards are overwhelming the session. Every card rotation hits word_intro because there are 531 unseen words and the cascade has NO probability gate — it always returns word_intro if an unseen word exists. Additionally, grammar concepts are generating "New word!" cards for things like "yo = I" and "tú = you", which feels pointless. There are also garbage entries in the seed data from broken markdown parsing.

## Three fixes:

### Fix 1: Add probability gate to word_intro in flow.py

In `select_next_card()`, the word_intro check (around line 307-324) currently always fires if an unseen word exists. Add a random probability gate so word_intro only appears ~25% of the time:

**Current code (around line 311):**
```python
    if intro_word:
        if forced_card_type in (None, "word_intro"):
            return FlowCardContext(
```

**Change to:**
```python
    if intro_word:
        if forced_card_type == "word_intro" or (forced_card_type is None and random.random() < 0.25):
            return FlowCardContext(
```

This matches the pattern used by word_match (~40%) and sentence_builder (~25%). Word intro cards will still appear, just not every single card.

### Fix 2: Mark grammar words as 'introduced' in seed_words.json

Grammar concept words shouldn't go through the "New word!" intro card flow. They're grammar elements taught via the teach card, not vocabulary to be individually introduced.

In `seed_words()` in `words.py`, when inserting words, check if the concept is a grammar concept. If so, insert with `status='introduced'` instead of `status='unseen'`. This means they skip the intro card and go straight to practice (where they can appear in word_practice, sentence_builder, etc.).

Add this set of grammar concept IDs to `words.py`:

```python
_GRAMMAR_CONCEPTS = frozenset({
    "subject_pronouns", "nouns_gender", "articles_definite", "articles_indefinite",
    "ser_present", "estar_present", "tener_present", "hay", "plurals",
    "possessive_adjectives", "demonstratives", "basic_questions",
    "adjective_agreement", "negation", "muy_mucho",
    "present_tense_ar", "present_tense_er_ir", "basic_prepositions",
    "telling_time", "frequency_adverbs", "ir_a", "gustar", "querer",
    "describing_people", "ordering_food", "asking_directions", "daily_routine",
    "tener_que_hay_que", "estar_gerund", "poder_infinitive", "conjunctions",
    "reflexive_verbs", "direct_object_pronouns", "indirect_object_pronouns",
    "comparatives", "present_perfect", "preterite_regular", "preterite_irregular",
    "imperfect_intro", "por_vs_para", "conditional_politeness", "imperative_basic",
})
```

Then in `seed_words()`, when inserting:
```python
initial_status = 'introduced' if concept_id in _GRAMMAR_CONCEPTS else 'unseen'
# Use initial_status instead of hardcoded 'unseen' in the INSERT
```

This means only VOCABULARY concepts (greetings, numbers_1_20, colors_basic, food_vocab, animals_vocab, numbers_21_100, clothing_vocab, body_parts, places_in_town, professions, weather_seasons, days_months, house_rooms, hobbies_free_time, shopping, health_doctor, travel_transport, my_city) will show word_intro cards.

### Fix 3: Clean garbage entries from seed_words.json

Remove broken entries from `data/seed_words.json` that were parsed incorrectly from markdown. Specifically delete any entries where:
- `spanish` contains `**` (markdown bold artifacts)
- `spanish` contains `usually end` or similar instruction text
- `spanish` is longer than 25 characters and contains `→` or `=`
- `english` contains `**` or `→`

Known garbage entries to remove:
- `nouns_gender`: "masculine**: usually end in", "feminine**: usually end in" (all 3 entries)
- `estar_gerund`: "estar** +"
- `present_perfect`: "he, has, ha, hemos, habéis, han" (duplicate long entries)

After cleanup, double-check that every remaining entry has sensible spanish/english values.

Also scan for and remove any entries where `spanish` == `english` (exact duplicates that add no value).

### Fix 4 (bonus): Update existing DB words

Since the user already has these words in their database as 'unseen', we need to update them too. In the `seed_words()` function, after the INSERT OR IGNORE, add an UPDATE for grammar concepts:

```python
# After the insert loop, update grammar concept words that are still 'unseen'
for concept_id in _GRAMMAR_CONCEPTS:
    conn.execute(
        """
        UPDATE words SET status = 'introduced', updated_at = ?
        WHERE concept_id = ? AND status = 'unseen'
        """,
        (timestamp, concept_id),
    )
```

This ensures existing databases get fixed too, not just fresh ones.

## Expected result

After these fixes:
- Word intro cards appear ~25% of the time (not 100%)
- Only vocabulary concepts show "New word!" cards (food, animals, colors, etc.)
- Grammar words are available for practice/match/sentence_builder but skip the intro step
- No more garbage entries with markdown artifacts
- Sessions feel balanced with a mix of card types instead of word_intro spam
