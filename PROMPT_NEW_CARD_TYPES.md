# PROMPT: New Card Types — Sentence Builder, Emoji Association, Fill-in-the-Blank

## Problem

Sessions are dominated by MCQs with the occasional conversation. Word cards (intro, practice, match) add some variety but are still multiple-choice. The moment-to-moment experience needs more game-like interactions to keep things fun and exercise different skills.

## Three New Card Types

### Card Type 1: Sentence Builder (`sentence_builder`)

**What it is:** Scrambled Spanish words that the user taps in order to build a correct sentence. Tests word order, grammar intuition, and reading comprehension. No AI needed — pure frontend game.

**Visual design:**
```
┌────────────────────────────────────┐
│  PRESENT TENSE — AR VERBS          │
│                                    │
│  Build the sentence                │
│                                    │
│  ┌──────────────────────────────┐  │
│  │  Yo estudio español.        │  │  ← Answer area (builds as user taps)
│  └──────────────────────────────┘  │
│                                    │
│  ┌────┐ ┌───────┐ ┌───────┐       │
│  │ .  │ │español│ │estudio│       │  ← Remaining tiles (shuffled)
│  └────┘ └───────┘ └───────┘       │
│                                    │
│  [Check Answer]                    │
└────────────────────────────────────┘
```

**Backend — `words.py`:**

Add function `build_sentence_builder_card(concept_id: str) -> dict | None`:

```python
def build_sentence_builder_card(concept_id: str) -> dict[str, Any] | None:
    """Build a sentence builder card from example sentences in the words table."""
    with _open_connection() as conn:
        rows = conn.execute(
            """
            SELECT example_sentence FROM words
            WHERE concept_id = ? AND example_sentence IS NOT NULL AND example_sentence != ''
            ORDER BY RANDOM()
            LIMIT 5
            """,
            (concept_id,),
        ).fetchall()

    # Find a good sentence (4-8 words, not too short, not too long)
    for row in rows:
        sentence = row["example_sentence"].strip()
        # Remove trailing period for cleaner tiles, we'll add it back
        clean = sentence.rstrip(".!?¡¿")
        words = clean.split()
        if 3 <= len(words) <= 8:
            punctuation = sentence[-1] if sentence[-1] in ".!?¡¿" else "."
            scrambled = words[:]
            # Keep shuffling until order is different from original
            for _ in range(20):
                random.shuffle(scrambled)
                if scrambled != words:
                    break
            return {
                "correct_words": words,
                "scrambled_words": scrambled,
                "punctuation": punctuation,  # The ending punctuation
                "correct_sentence": " ".join(words) + punctuation,
            }
    return None
```

**FlowCardContext — `models.py`:**

Add these fields to the FlowCardContext dataclass:
```python
    scrambled_words: list[str] = field(default_factory=list)    # For sentence_builder
    correct_sentence: str = ""                                   # For sentence_builder
```

**Card selection — `flow.py`:**

In `select_next_card()`, add sentence_builder AFTER word_match and BEFORE word_practice (around line 326). It should appear with ~25% probability when the concept has enough example sentences:

```python
# Sentence builder card — 25% chance if example sentences available
if forced_card_type in (None, "sentence_builder"):
    from .words import build_sentence_builder_card
    sb_card = build_sentence_builder_card(concept_id)
    if sb_card and (forced_card_type == "sentence_builder" or (forced_card_type is None and random.random() < 0.25)):
        return FlowCardContext(
            card_type="sentence_builder",
            concept_id=concept_id,
            question="Build the sentence",
            correct_answer=sb_card["correct_sentence"],
            scrambled_words=sb_card["scrambled_words"],
            correct_sentence=sb_card["correct_sentence"],
            interest_topics=interest_topic_names,
        )
```

Add `"sentence_builder"` to `_FORCEABLE_CARD_TYPES`.

**Template — `flow_card.html`:**

Add a new `{% elif card_context.card_type == 'sentence_builder' %}` block. This card needs inline JavaScript for the tap-to-build interaction:

```html
{% elif card_context.card_type == 'sentence_builder' %}
<div class="flow-card-enter rounded-2xl bg-[#1a2d35] p-6 shadow-lg shadow-black/20 ring-1 ring-amber-500/20" id="sb-card">
  <header class="flex items-center justify-between mb-4">
    <span class="rounded-full bg-amber-500/15 px-3 py-1 text-xs font-bold uppercase tracking-wide text-amber-300">
      {{ concept_name }}
    </span>
  </header>

  <p class="text-sm font-bold uppercase tracking-[0.2em] text-amber-300 mb-3">Build the sentence</p>

  <!-- Answer area: words appear here as user taps -->
  <div id="sb-answer" class="min-h-[3.5rem] rounded-xl bg-[#0f1a1f] px-4 py-3 mb-4 flex flex-wrap gap-2 items-center">
    <span class="text-slate-500 text-sm" id="sb-placeholder">Tap words in order...</span>
  </div>

  <!-- Scrambled word tiles -->
  <div id="sb-tiles" class="flex flex-wrap gap-2 mb-6 justify-center">
    {% for word in card_context.scrambled_words %}
      <button type="button"
        class="sb-tile rounded-lg bg-[#162028] px-4 py-2.5 text-lg font-medium text-slate-200 transition hover:bg-amber-500/20 hover:ring-1 hover:ring-amber-500/30 active:scale-95"
        data-word="{{ word }}"
        onclick="sbTap(this)">
        {{ word }}
      </button>
    {% endfor %}
  </div>

  <!-- Submit form (hidden until ready) -->
  <form hx-post="/flow/answer" hx-target="#flow-card-slot" hx-swap="innerHTML" id="sb-form">
    <input type="hidden" name="session_id" value="{{ session_id }}" />
    <input type="hidden" name="card_json" value='{{ card_json }}' />
    <input type="hidden" name="chosen_option" value="" id="sb-chosen" />
    <input type="hidden" name="start_time" value="0" />
    <button type="submit" id="sb-submit"
      class="w-full rounded-xl bg-amber-500 px-6 py-3.5 text-base font-black text-amber-950 shadow-lg shadow-amber-500/25 transition hover:bg-amber-400 active:scale-[0.98] opacity-50 pointer-events-none"
      disabled>
      Check Answer
    </button>
  </form>
</div>

<script>
(function() {
  var chosen = [];
  var tiles = document.querySelectorAll('.sb-tile');
  var answerArea = document.getElementById('sb-answer');
  var placeholder = document.getElementById('sb-placeholder');
  var submitBtn = document.getElementById('sb-submit');
  var chosenInput = document.getElementById('sb-chosen');
  var totalWords = tiles.length;

  window.sbTap = function(btn) {
    // Move word from tiles to answer area
    var word = btn.getAttribute('data-word');
    chosen.push(word);
    btn.classList.add('hidden');

    // Add to answer area
    if (placeholder) placeholder.classList.add('hidden');
    var span = document.createElement('span');
    span.className = 'rounded-lg bg-amber-500/20 px-3 py-1.5 text-lg font-medium text-slate-100 cursor-pointer transition hover:bg-red-500/20';
    span.textContent = word;
    span.setAttribute('data-idx', chosen.length - 1);
    span.onclick = function() { sbRemove(this); };
    answerArea.appendChild(span);

    // Enable submit when all words placed
    if (chosen.length === totalWords) {
      submitBtn.disabled = false;
      submitBtn.classList.remove('opacity-50', 'pointer-events-none');
      chosenInput.value = chosen.join(' ');
    }
  };

  window.sbRemove = function(span) {
    var idx = parseInt(span.getAttribute('data-idx'));
    var word = chosen[idx];
    chosen.splice(idx, 1);
    span.remove();

    // Re-show the tile
    tiles.forEach(function(t) {
      if (t.getAttribute('data-word') === word && t.classList.contains('hidden')) {
        t.classList.remove('hidden');
      }
    });

    // Re-index remaining spans
    var spans = answerArea.querySelectorAll('span[data-idx]');
    spans.forEach(function(s, i) { s.setAttribute('data-idx', i); });

    // Show placeholder if empty
    if (chosen.length === 0 && placeholder) placeholder.classList.remove('hidden');

    // Disable submit
    submitBtn.disabled = true;
    submitBtn.classList.add('opacity-50', 'pointer-events-none');
    chosenInput.value = '';
  };
})();
</script>
```

**Answer handling:**

The sentence builder reuses the existing `/flow/answer` endpoint. The `chosen_option` is the user's assembled sentence (words joined with spaces). The `correct_answer` in card_json is the correct sentence. `process_mcq_answer()` compares them — if they match, it's correct.

**Important:** The comparison should be case-insensitive. In `process_mcq_answer()` (flow.py), the grading line is:
```python
is_correct = chosen_option == card_context.correct_answer
```
Change this to case-insensitive comparison:
```python
is_correct = chosen_option.strip().lower() == card_context.correct_answer.strip().lower()
```
This benefits ALL card types (MCQ answers are already exact matches, so it's safe).

---

### Card Type 2: Emoji Association (`emoji_association`)

**What it is:** A big emoji is displayed. User picks the correct Spanish word from 4 options. Fast, visual, low-stakes. Great for vocabulary reinforcement. Uses the emoji data from seed_words.json.

**Visual design:**
```
┌────────────────────────────────────┐
│  FOOD VOCABULARY                   │
│                                    │
│  What's this word?                 │
│                                    │
│           🍎                       │  ← Big emoji
│                                    │
│  ┌──────────┐  ┌──────────┐       │
│  │ manzana  │  │  queso   │       │  ← 4 options (Spanish words)
│  └──────────┘  └──────────┘       │
│  ┌──────────┐  ┌──────────┐       │
│  │   pan    │  │   agua   │       │
│  └──────────┘  └──────────┘       │
└────────────────────────────────────┘
```

**Backend — `words.py`:**

Add function `build_emoji_card(concept_id: str) -> dict | None`:

```python
def build_emoji_card(concept_id: str) -> dict[str, Any] | None:
    """Build an emoji association card. Pick a word with emoji + 3 distractors."""
    with _open_connection() as conn:
        # Get words with emojis from this concept
        target_rows = conn.execute(
            """
            SELECT * FROM words
            WHERE concept_id = ? AND emoji IS NOT NULL AND emoji != ''
              AND status IN ('introduced', 'practicing', 'known')
            ORDER BY RANDOM()
            LIMIT 1
            """,
            (concept_id,),
        ).fetchall()
        if not target_rows:
            return None

        target = target_rows[0]

        # Get 3 distractors (different words from same concept, or any concept)
        distractors = conn.execute(
            """
            SELECT spanish FROM words
            WHERE id != ? AND emoji IS NOT NULL AND emoji != ''
              AND status IN ('introduced', 'practicing', 'known')
            ORDER BY RANDOM()
            LIMIT 3
            """,
            (target["id"],),
        ).fetchall()

    if len(distractors) < 3:
        return None

    options = [target["spanish"]] + [d["spanish"] for d in distractors]
    random.shuffle(options)
    return {
        "word_id": target["id"],
        "emoji": target["emoji"],
        "correct_spanish": target["spanish"],
        "english_hint": target["english"],
        "options": options,
    }
```

**Card selection — `flow.py`:**

Add emoji_association AFTER sentence_builder, with ~20% probability:

```python
# Emoji association card — 20% chance if words with emojis exist
if forced_card_type in (None, "emoji_association"):
    from .words import build_emoji_card
    emoji_card = build_emoji_card(concept_id)
    if emoji_card and (forced_card_type == "emoji_association" or (forced_card_type is None and random.random() < 0.20)):
        return FlowCardContext(
            card_type="emoji_association",
            concept_id=concept_id,
            question="What's this word?",
            correct_answer=emoji_card["correct_spanish"],
            options=emoji_card["options"],
            word_id=emoji_card["word_id"],
            word_emoji=emoji_card["emoji"],
            word_english=emoji_card["english_hint"],
            interest_topics=interest_topic_names,
        )
```

Add `"emoji_association"` to `_FORCEABLE_CARD_TYPES`.

**Template — `flow_card.html`:**

Add a new block. This card uses the standard MCQ answer flow (individual form per option, submits to `/flow/answer`):

```html
{% elif card_context.card_type == 'emoji_association' %}
<div class="flow-card-enter rounded-2xl bg-[#1a2d35] p-6 shadow-lg shadow-black/20 ring-1 ring-pink-500/20">
  <header class="flex items-center justify-between mb-4">
    <span class="rounded-full bg-pink-500/15 px-3 py-1 text-xs font-bold uppercase tracking-wide text-pink-300">
      {{ concept_name }}
    </span>
  </header>

  <p class="text-sm font-bold uppercase tracking-[0.2em] text-pink-300 mb-2">{{ card_context.question }}</p>

  <div class="text-center my-6">
    <p class="text-7xl">{{ card_context.word_emoji }}</p>
  </div>

  <div class="grid grid-cols-2 gap-3">
    {% for option in card_context.options %}
      <form hx-post="/flow/answer" hx-target="#flow-card-slot" hx-swap="innerHTML">
        <input type="hidden" name="session_id" value="{{ session_id }}" />
        <input type="hidden" name="card_json" value='{{ card_json }}' />
        <input type="hidden" name="chosen_option" value="{{ option }}" />
        <input type="hidden" name="start_time" value="0" />
        <button type="submit"
          class="w-full text-center rounded-xl bg-[#0f1a1f] px-4 py-4 text-lg font-semibold text-slate-200 transition hover:bg-[#162028] hover:ring-1 hover:ring-pink-500/30 active:scale-[0.98] active:bg-pink-500/10">
          {{ option }}
        </button>
      </form>
    {% endfor %}
  </div>
</div>
```

**Answer handling:** Reuses `/flow/answer` endpoint exactly like MCQ. Also call `mark_word_practice_result(word_id, is_correct)` when word_id is present (same as word_practice handling).

In `flow_routes.py`, in the `flow_answer()` function, the existing word_practice handling already checks for word_id:
```python
if card_context.word_id:
    mark_word_practice_result(card_context.word_id, result.is_correct)
```
Emoji association cards set word_id, so this will automatically work.

---

### Card Type 3: Fill-in-the-Blank — Grammar (`fill_blank`)

**What it is:** A full Spanish sentence with one GRAMMAR word blanked out, 4 grammatically plausible options. Different from word_practice (which blanks vocabulary nouns/verbs) — this blanks articles, verb conjugations, prepositions, pronouns. Tests grammar application in context.

**Visual design:**
```
┌────────────────────────────────────┐
│  SER — PRESENT TENSE               │
│                                    │
│  Complete the sentence             │
│                                    │
│  Ella ______ de México.            │  ← Sentence with highlighted blank
│                                    │
│  ┌──────┐  ┌──────┐               │
│  │  es  │  │ está │               │  ← 4 grammar options
│  └──────┘  └──────┘               │
│  ┌──────┐  ┌──────┐               │
│  │  son │  │ soy  │               │
│  └──────┘  └──────┘               │
└────────────────────────────────────┘
```

**Backend — `words.py`:**

This card type works differently from others. Instead of pulling from the words table, it uses **pre-built fill-in-the-blank items** stored in a new JSON data file.

**Create `data/fill_blanks.json`:**

A JSON file with grammar-focused fill-in-the-blank items per concept. Each item has a sentence, the blanked word, and 3 distractors:

```json
{
  "ser_present": [
    {
      "sentence": "Ella ___ de México.",
      "answer": "es",
      "distractors": ["está", "son", "soy"]
    },
    {
      "sentence": "Nosotros ___ estudiantes.",
      "answer": "somos",
      "distractors": ["son", "es", "estamos"]
    }
  ],
  "estar_present": [
    {
      "sentence": "Yo ___ en casa.",
      "answer": "estoy",
      "distractors": ["soy", "está", "es"]
    }
  ],
  "articles_definite": [
    {
      "sentence": "___ libros están en la mesa.",
      "answer": "Los",
      "distractors": ["Las", "El", "La"]
    }
  ]
}
```

**Create 4-8 items per grammar concept.** Focus on concepts where there's a meaningful choice between similar forms: ser/estar, articles, verb conjugations, prepositions, pronouns. Vocabulary concepts (food_vocab, animals_vocab, etc.) generally DON'T need fill_blank items since word_practice already covers them. But some communicative concepts like ordering_food can have useful ones ("_____ un café, por favor" → Quiero/Tengo/Puedo/Hago).

Target: ~150-200 fill-blank items across grammar concepts.

Add function `build_fill_blank_card(concept_id: str) -> dict | None`:

```python
import json
from pathlib import Path

_FILL_BLANKS_PATH = Path(__file__).parent.parent.parent / "data" / "fill_blanks.json"
_FILL_BLANKS_CACHE: dict | None = None

def _load_fill_blanks() -> dict:
    global _FILL_BLANKS_CACHE
    if _FILL_BLANKS_CACHE is None:
        if _FILL_BLANKS_PATH.exists():
            _FILL_BLANKS_CACHE = json.loads(_FILL_BLANKS_PATH.read_text(encoding="utf-8"))
        else:
            _FILL_BLANKS_CACHE = {}
    return _FILL_BLANKS_CACHE


def build_fill_blank_card(concept_id: str) -> dict[str, Any] | None:
    """Build a grammar fill-in-the-blank card from pre-authored items."""
    blanks = _load_fill_blanks()
    items = blanks.get(concept_id, [])
    if not items:
        return None

    item = random.choice(items)
    options = [item["answer"]] + item["distractors"]
    random.shuffle(options)
    return {
        "sentence": item["sentence"],
        "correct_answer": item["answer"],
        "options": options,
    }
```

**Card selection — `flow.py`:**

Add fill_blank BEFORE the MCQ fallback, with ~30% probability. It should be preferred over MCQ for grammar concepts that have fill_blank data:

```python
# Fill-in-the-blank (grammar) — 30% chance if items exist for this concept
if forced_card_type in (None, "fill_blank"):
    from .words import build_fill_blank_card
    fb_card = build_fill_blank_card(concept_id)
    if fb_card and (forced_card_type == "fill_blank" or (forced_card_type is None and random.random() < 0.30)):
        return FlowCardContext(
            card_type="fill_blank",
            concept_id=concept_id,
            question="Complete the sentence",
            correct_answer=fb_card["correct_answer"],
            options=fb_card["options"],
            word_sentence=fb_card["sentence"],  # Reuse word_sentence field for the sentence
            interest_topics=interest_topic_names,
        )
```

Add `"fill_blank"` to `_FORCEABLE_CARD_TYPES`.

**Template — `flow_card.html`:**

```html
{% elif card_context.card_type == 'fill_blank' %}
{% set concept_toggle = concept_teach_html is defined and concept_teach_html %}
<div class="flow-card-enter rounded-2xl bg-[#1a2d35] p-6 shadow-lg shadow-black/20 ring-1 ring-cyan-500/20" data-concept-wrapper>
  <header class="flex items-center justify-between mb-4">
    {% if concept_toggle %}
      <button type="button" class="flex items-center gap-2 rounded-full bg-cyan-500/15 px-3 py-1 text-xs font-bold uppercase tracking-wide text-cyan-300 transition hover:bg-cyan-500/25" data-concept-toggle aria-expanded="false">
        <span>{{ concept_name }}</span>
        <span class="text-[10px] text-cyan-200 font-normal normal-case">View lesson</span>
      </button>
    {% else %}
      <span class="rounded-full bg-cyan-500/15 px-3 py-1 text-xs font-bold uppercase tracking-wide text-cyan-300">
        {{ concept_name }}
      </span>
    {% endif %}
  </header>

  {% if concept_toggle %}
    <div class="hidden rounded-2xl border border-cyan-500/20 bg-[#0f1a1f] px-4 py-3 mb-5" data-concept-panel>
      <p class="text-[11px] uppercase tracking-wide text-cyan-400 font-bold mb-2">Lesson snippet</p>
      <div class="prose prose-invert prose-sm max-w-none text-slate-300">
        {{ concept_teach_html | safe }}
      </div>
    </div>
  {% endif %}

  <p class="text-sm font-bold uppercase tracking-[0.2em] text-cyan-300 mb-2">{{ card_context.question }}</p>

  <div class="mb-6">
    <p class="text-2xl font-bold text-slate-50 leading-snug">{{ card_context.word_sentence }}</p>
  </div>

  <div class="grid grid-cols-2 gap-3">
    {% for option in card_context.options %}
      <form hx-post="/flow/answer" hx-target="#flow-card-slot" hx-swap="innerHTML">
        <input type="hidden" name="session_id" value="{{ session_id }}" />
        <input type="hidden" name="card_json" value='{{ card_json }}' />
        <input type="hidden" name="chosen_option" value="{{ option }}" />
        <input type="hidden" name="start_time" value="0" />
        <button type="submit"
          class="w-full text-center rounded-xl bg-[#0f1a1f] px-4 py-4 text-lg font-semibold text-slate-200 transition hover:bg-[#162028] hover:ring-1 hover:ring-cyan-500/30 active:scale-[0.98] active:bg-cyan-500/10">
          {{ option }}
        </button>
      </form>
    {% endfor %}
  </div>
</div>
```

**Answer handling:** Reuses `/flow/answer` exactly like MCQ. Correct/incorrect is graded by comparing `chosen_option` with `correct_answer`. BKT gets updated for the concept.

---

## Summary of Changes

### New files to create:
- `data/fill_blanks.json` — ~150-200 grammar fill-in-the-blank items across grammar concepts

### Files to modify:

**`src/spanish_vibes/models.py`** — Add to FlowCardContext:
- `scrambled_words: list[str] = field(default_factory=list)`
- `correct_sentence: str = ""`

**`src/spanish_vibes/words.py`** — Add 3 new functions:
- `build_sentence_builder_card(concept_id)`
- `build_emoji_card(concept_id)`
- `build_fill_blank_card(concept_id)`

**`src/spanish_vibes/flow.py`** — In `select_next_card()`:
- Add `"sentence_builder"`, `"emoji_association"`, `"fill_blank"` to `_FORCEABLE_CARD_TYPES`
- Add selection logic for all 3 new types in the cascade (after word cards, before MCQ)
- Import the new build functions from words.py
- Make MCQ answer comparison case-insensitive (for sentence_builder)

**`templates/partials/flow_card.html`** — Add 3 new template blocks:
- `sentence_builder` (with inline JS for tap-to-build)
- `emoji_association` (2x2 grid of options with big emoji)
- `fill_blank` (sentence with blank + 2x2 grid of grammar options)

**`src/spanish_vibes/flow_routes.py`**:
- In `flow_answer()`, add word_id handling for emoji_association (already works if word_id is in card_json)
- Make sure `card_json` serialization includes `scrambled_words` and `correct_sentence` for sentence_builder

### Updated card cascade order in select_next_card():
1. Force conversation/story (dev override)
2. Auto-inject conversation (every N cards)
3. Force teach (dev override)
4. Auto teach (new concepts)
5. **Word intro** (~40% if unseen words exist)
6. **Word match** (~40% if 3+ known words)
7. **Sentence builder** (~25% if example sentences exist) ← NEW
8. **Emoji association** (~20% if words with emojis exist) ← NEW
9. **Word practice** (if introduced/practicing words exist)
10. **Fill-in-the-blank** (~30% if items exist for concept) ← NEW
11. **MCQ** (always available fallback)

### Color theming per card type (ring + accent colors):
- Teach: `sky-500`
- Story: `violet-500`
- Word intro: `violet-500`
- Word practice: `emerald-500`
- Word match: `emerald-500`
- Sentence builder: `amber-500` ← NEW
- Emoji association: `pink-500` ← NEW
- Fill-in-the-blank: `cyan-500` ← NEW
- MCQ: `emerald-500`

### Probability balancing:

The percentages are "chance of selecting this type IF data is available." Since they're checked in cascade order, later types only fire if earlier ones didn't. The actual distribution in practice will be:
- ~10-15% word intro (early in learning)
- ~10% word match
- ~8-10% sentence builder
- ~5-8% emoji association
- ~10-15% word practice
- ~10-15% fill-in-the-blank
- ~25-30% MCQ (the fallback)
- ~15-20% conversation (every 5th card)

This gives much more variety than the current MCQ-dominant experience.

## fill_blanks.json Content Guidelines

Create items for ALL grammar concepts. Here are the concepts that should have fill_blank items:

**High priority (core grammar — 6-8 items each):**
- ser_present, estar_present, tener_present, hay
- articles_definite, articles_indefinite
- present_tense_ar, present_tense_er_ir
- gustar, querer, ir_a
- adjective_agreement, negation

**Medium priority (4-6 items each):**
- subject_pronouns, possessive_adjectives, demonstratives
- basic_prepositions, por_vs_para
- direct_object_pronouns, indirect_object_pronouns
- reflexive_verbs, estar_gerund, poder_infinitive
- comparatives, conjunctions
- tener_que_hay_que, muy_mucho

**Lower priority (3-4 items each):**
- present_perfect, preterite_regular, preterite_irregular, imperfect_intro
- conditional_politeness, imperative_basic
- frequency_adverbs, plurals, basic_questions

**Communicative concepts (2-4 items each):**
- ordering_food, asking_directions, daily_routine, describing_people, shopping

Each item's distractors should be **grammatically plausible but wrong** — not random words. For ser/estar, distractors are other forms of ser/estar. For articles, distractors are other articles. This is what makes the card educational.

## Testing

1. Delete DB, restart app, play through a session
2. Verify all 3 new card types appear in the mix
3. Sentence builder: check that tapping works, removing works, submit grades correctly
4. Emoji association: check that emoji displays large, 2x2 grid looks good on mobile
5. Fill-in-blank: check that grammar distractors make sense, correct answer is accepted
6. Dev panel should show new card types (data-dev-card-type attribute already set)
7. Force each card type via dev override to test in isolation
