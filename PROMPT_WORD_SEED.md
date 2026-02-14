# PROMPT: Seed Vocabulary for All Concepts

## Problem

The word system is starved. Only 16 seed words exist across 4 concepts (greetings, numbers_1_20, colors_basic, food_vocab), while 48 concepts exist in `data/concepts.yaml`. Without words, the word_intro, word_practice, and word_match card types never appear for most concepts. The entire word pipeline sits idle.

## Design Principles

- Every concept should have 6-12 seed words extracted from its `teach_content`
- Words should have emojis where a natural visual exists (nouns, actions, objects)
- Grammar concepts get key vocabulary too (verb forms, pronouns, question words)
- Domain-specific words get a `topic_slug` linking to interest_topics for interest-driven prioritization
- Core/function words (pronouns, articles, conjunctions) get `topic_slug: null` — they're universal
- Example sentences should be simple A1-A2 level, using the word in natural context

## Changes Required

### Change 1: Create `data/seed_words.json`

Create a JSON file at `data/seed_words.json` containing ALL vocabulary for ALL 48 concepts. Use the `teach_content` in `data/concepts.yaml` as the primary source — the Spanish-English pairs are already there in bold.

**Format:**
```json
{
  "greetings": [
    {
      "spanish": "hola",
      "english": "hello",
      "emoji": "👋",
      "example": "Hola, ¿cómo estás?",
      "topic_slug": null
    },
    {
      "spanish": "buenos días",
      "english": "good morning",
      "emoji": "🌅",
      "example": "Buenos días, profesor.",
      "topic_slug": null
    }
  ],
  "food_vocab": [
    {
      "spanish": "pan",
      "english": "bread",
      "emoji": "🍞",
      "example": "El pan está caliente.",
      "topic_slug": "food-cooking"
    }
  ]
}
```

**Topic slug mapping** — use these slugs from the `interest_topics` table. Only assign a topic_slug when the word is clearly domain-specific. Core/grammar words should be null:

| Concept | topic_slug |
|---|---|
| food_vocab | food-cooking |
| ordering_food | food-cooking |
| animals_vocab | nature-animals |
| clothing_vocab | fashion |
| body_parts | health |
| professions | business |
| family_vocab | relationships |
| hobbies_free_time | sports (sport words), music (music words), gaming (game words) — use judgment per word |
| weather_seasons | nature-animals |
| places_in_town | travel |
| travel_transport | travel |
| shopping | fashion |
| health_doctor | health |
| my_city | travel |
| house_rooms | null (universal) |
| describing_people | null (universal) |
| daily_routine | null (universal) |
| All grammar concepts | null |

**Concept-by-concept extraction guide:**

For VOCABULARY concepts (greetings, numbers_1_20, colors_basic, family_vocab, food_vocab, animals_vocab, numbers_21_100, clothing_vocab, body_parts, places_in_town, professions, weather_seasons, days_months, house_rooms, hobbies_free_time, shopping, health_doctor, travel_transport, my_city):
- Extract ALL Spanish-English pairs from teach_content
- Add an emoji for each word (noun emoji, color emoji, number emoji, etc.)
- Write a simple example sentence for each

For GRAMMAR concepts (subject_pronouns, nouns_gender, articles_definite, articles_indefinite, ser_present, tener_present, hay, plurals, possessive_adjectives, demonstratives, basic_questions, adjective_agreement, negation, muy_mucho, estar_present, ir_a, gustar, querer, present_tense_ar, present_tense_er_ir, basic_prepositions, telling_time, frequency_adverbs, describing_people, ordering_food, asking_directions, daily_routine, tener_que_hay_que, estar_gerund, poder_infinitive, conjunctions, reflexive_verbs, direct_object_pronouns, indirect_object_pronouns, comparatives, present_perfect, preterite_regular, preterite_irregular, imperfect_intro, por_vs_para, conditional_politeness, imperative_basic):
- Extract the KEY vocabulary (verb infinitives, question words, prepositions, adverbs, key phrases)
- For verb concepts, include the infinitive + key conjugated forms as separate entries where useful
- For communicative concepts (ordering_food, asking_directions, daily_routine), extract the phrases/vocabulary
- Keep it to 6-10 words per grammar concept — don't over-seed

**Multi-word entries are fine** — "buenos días", "por favor", "mucho gusto" are all valid entries. The `spanish` field stores them as-is.

### Change 2: Add `topic_slug` column to words table

In `db.py`, in the `_init_tables_words()` function, add a `topic_slug TEXT` column to the words table:

```sql
CREATE TABLE IF NOT EXISTS words (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    spanish TEXT NOT NULL UNIQUE,
    english TEXT NOT NULL,
    emoji TEXT,
    example_sentence TEXT,
    concept_id TEXT,
    topic_slug TEXT,
    status TEXT NOT NULL DEFAULT 'unseen',
    mastery_score REAL NOT NULL DEFAULT 0.0,
    times_seen INTEGER NOT NULL DEFAULT 0,
    times_correct INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
```

Also add an index: `CREATE INDEX IF NOT EXISTS idx_words_topic ON words(topic_slug)`

Since SQLite doesn't support ALTER TABLE ADD COLUMN cleanly in all cases, and this is a dev app, add the column via a migration-style approach. After the CREATE TABLE, add:
```python
try:
    connection.execute("ALTER TABLE words ADD COLUMN topic_slug TEXT")
except Exception:
    pass  # Column already exists
```

### Change 3: Update `seed_words()` in `words.py`

Replace the hardcoded `SEED_WORDS` dict. Load from the JSON file instead:

```python
import json
from pathlib import Path

def seed_words() -> int:
    """Seed words from data/seed_words.json. Returns count of words inserted."""
    seed_file = Path(__file__).parent.parent.parent / "data" / "seed_words.json"
    if not seed_file.exists():
        return 0

    with open(seed_file) as f:
        all_words = json.load(f)

    timestamp = now_iso()
    seeded = 0
    with _open_connection() as conn:
        for concept_id, entries in all_words.items():
            for entry in entries:
                spanish = _normalize_spanish(entry["spanish"])
                english = entry["english"].strip()
                emoji = entry.get("emoji")
                example = entry.get("example")
                topic_slug = entry.get("topic_slug")
                result = conn.execute(
                    """
                    INSERT OR IGNORE INTO words
                    (spanish, english, emoji, example_sentence, concept_id, topic_slug, status, mastery_score, times_seen, times_correct, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, 'unseen', 0.0, 0, 0, ?, ?)
                    """,
                    (spanish, english, emoji, example, concept_id, topic_slug, timestamp, timestamp),
                )
                if result.rowcount > 0:
                    seeded += 1
        conn.commit()
    return seeded
```

Keep the old `SEED_WORDS` dict removed or commented out. The JSON file is the single source of truth now.

Also update the `Word` dataclass to include `topic_slug`:
```python
@dataclass(slots=True)
class Word:
    id: int
    spanish: str
    english: str
    emoji: str | None
    example_sentence: str | None
    concept_id: str | None
    topic_slug: str | None
    status: str
    times_seen: int
    times_correct: int
```

Update `_row_to_word()` to include `topic_slug` from the row.

Also update the inline `Word(...)` construction in `build_match_card()` (around line 246) to include `topic_slug=row["topic_slug"]`.

### Change 4: Interest-aware word intro selection

Update `get_intro_candidate()` to optionally prefer words from high-interest topics.

Add a new function:

```python
def get_intro_candidate_weighted(concept_id: str, top_interest_slugs: list[str] | None = None) -> Word | None:
    """Pick an unseen word, preferring words from high-interest topics.

    If top_interest_slugs is provided and there are matching unseen words,
    return one of those. Otherwise fall back to chronological order.
    """
    with _open_connection() as conn:
        # First try: unseen word matching a high-interest topic
        if top_interest_slugs:
            placeholders = ",".join("?" for _ in top_interest_slugs)
            row = conn.execute(
                f"""
                SELECT * FROM words
                WHERE concept_id = ? AND status = 'unseen' AND topic_slug IN ({placeholders})
                ORDER BY created_at
                LIMIT 1
                """,
                (concept_id, *top_interest_slugs),
            ).fetchone()
            if row:
                return _row_to_word(row)

        # Fallback: any unseen word for this concept
        row = conn.execute(
            """
            SELECT * FROM words
            WHERE concept_id = ? AND status = 'unseen'
            ORDER BY created_at
            LIMIT 1
            """,
            (concept_id,),
        ).fetchone()
    if row is None:
        return None
    return _row_to_word(row)
```

### Change 5: Wire interest-aware selection into flow.py

In `flow.py`, in the `select_next_card()` function, where `get_intro_candidate(concept_id)` is called (around line 297), change it to use the weighted version:

```python
from .words import get_intro_candidate_weighted

# Get user's top interest topic slugs for word prioritization
top_interest_slugs = None
try:
    from .interest import InterestTracker
    tracker = InterestTracker()
    top_interests = tracker.get_top_interests(n=5)
    if top_interests:
        top_interest_slugs = [t["slug"] for t in top_interests if "slug" in t]
except Exception:
    pass

intro_word = get_intro_candidate_weighted(concept_id, top_interest_slugs)
```

Keep the existing `get_intro_candidate()` function as-is for backward compatibility, but the flow now uses the weighted version.

### Change 6: Update harvest_conversation_words to set topic_slug

In `words.py`, in `harvest_conversation_words()`, when inserting new words discovered from conversation, also try to set the topic_slug based on the concept_id:

```python
# When inserting a new word from conversation:
topic_slug = None
if concept_id:
    # Look up topic for this concept
    from .interest import CONCEPT_TOPIC_MAP
    from .db import get_interest_topic_by_slug
    mapped_slug = CONCEPT_TOPIC_MAP.get(concept_id)
    if mapped_slug:
        topic = get_interest_topic_by_slug(mapped_slug)
        if topic:
            topic_slug = mapped_slug
```

Add topic_slug to the INSERT statement for new conversation words.

## Testing

After implementation:
1. Delete the existing `instance/spanish_vibes.db` (or just the words from it) and restart the app
2. Check that `seed_words()` populates ~400+ words across all concepts
3. Verify word_intro cards appear for previously empty concepts (e.g. family_vocab, animals_vocab)
4. Verify emojis display on word cards
5. Verify topic_slug is set on domain-specific words

## Important Notes

- Use `INSERT OR IGNORE` for seeding — don't overwrite words that already exist (user may have progressed)
- The JSON file should be human-readable and maintainable — format it nicely with 2-space indentation
- Multi-word phrases are fine as entries (e.g. "buenos días", "mucho gusto", "a la derecha")
- For grammar concepts, don't seed every conjugated form — seed the infinitive and 2-3 key forms
- Total target: ~400-500 words across all 48 concepts
