# Spanish Vibes — Continuation Prompt

## What is this project?

**Spanish Vibes** is a TikTok-inspired, free Spanish language learning app (A1–A2 level). It uses a low-agency content delivery model — users are served educational content in an infinite-scroll flow rather than choosing what to learn. Think Duolingo meets TikTok.

**Tech stack:** Python 3.11+, FastAPI, Jinja2 templates, HTMX, Tailwind CSS, SQLite, OpenAI API (gpt-4o-mini for MCQs, gpt-4o for conversation corrections).

**Code lives in:** `src/spanish_vibes/` (19 modules). Templates in `templates/` and `templates/partials/`. Concept definitions in `data/concepts.yaml`. DB is SQLite at `data/spanish_vibes.db`. Build/run with `uv sync` and `uv run`.

**Key project files:**
- `BACKLOG.md` — Concrete tasks, ordered by priority. Check this first.
- `DESIGN_IDEAS.md` — Bigger-picture design thinking: persona system, memory, enjoyment scoring, adaptive placement, interest-driven vocabulary, technical architecture. Read this for context on WHY things are designed the way they are.
- `AGENTS.md` — Coding conventions, build commands, testing.

## Current architecture

### Card types (3 today)

1. **Teach** — Markdown lesson shown once per concept before MCQs begin. Marked `teach_shown=1` after viewing.
2. **MCQ** — Multiple choice question. AI-generated via gpt-4o-mini, cached in `flow_mcq_cache` table. Each has 1 correct answer + 3 distractors with misconception mappings. Recently improved prompt to avoid ambiguous questions + post-generation `_validate_mcq()` filter.
3. **Conversation** — AI chat with "Marta" persona (currently hardcoded). Injected every 5 MCQ cards for concepts with ≥3 attempts. Full message history, inline corrections, vocabulary gap tracking, post-conversation summary with correction stepper.

### Card selection (`flow.py` → `select_next_card()`)

Weighted bucket system:
- 30% spot-check (mastered concepts)
- 50% practice (learning concepts, sorted by lowest p_mastery)
- 20% new (unseen concepts with prerequisites met)
- Conversation injection every 5 cards (only for concepts with ≥3 attempts)
- Teach card on first encounter with any concept

### Key models (`models.py`)

```python
FlowCardContext:
    card_type: str            # 'mcq' | 'teach' | 'conversation'
    concept_id: str
    question: str
    correct_answer: str
    options: list[str]        # 4 MCQ choices
    option_misconceptions: dict[str, str]
    difficulty: int           # 1–3
    mcq_card_id: int | None
    teach_content: str
    interest_topics: list[str]

ConceptKnowledge:
    concept_id, p_mastery, n_attempts, n_correct, n_wrong, teach_shown, last_seen_at

MCQCard:
    id, concept_id, question, correct_answer, distractors (list[dict]), difficulty, times_used, content_hash, source
```

### Mastery system

- **Bayesian Knowledge Tracing (BKT)** in `bkt.py` — updates p_mastery per concept
- Mastered = p_mastery ≥ 0.90 AND n_attempts ≥ 5
- Prerequisites enforced: new concepts only unlock when all prereqs are mastered
- Concept DAG defined in `data/concepts.yaml` with topological sort validation

### Interest tracking (`interest.py`)

Signals captured on every card interaction (correctness, dwell time, return frequency). Exponential moving average scoring with 45-day decay half-life. Feeds topic/theme selection for conversations and themed MCQs. ~20 seeded topics (Sports, Music, Food, Travel, etc.).

### Existing DB tables (relevant to upcoming work)

- `vocabulary_gaps` — Words discovered during conversations: english_word, spanish_word, concept_id, source, times_seen, times_correct. UNIQUE(english_word, spanish_word). Already wired to call `record_word_gap()` from `words.py` on insert.
- `flow_mcq_cache` — Cached AI-generated MCQs per concept
- `concept_knowledge` — BKT state per concept
- `flow_conversations` — Full conversation history with messages_json, corrections_json, score, persona tracking
- `interest_topics` + `user_interest_scores` + `card_signals` — Interest tracking

### Module map

```
app.py              — FastAPI main app, home/quiz routes
web.py              — Lesson browsing routes
flow.py             — Core flow engine: BKT scheduling, card selection
flow_routes.py      — /flow/* endpoints (card, answer, conversation, stats, concepts)
flow_ai.py          — AI MCQ generation + teach card generation + conversation openers
flow_db.py          — Flow DB operations (sessions, responses, concept knowledge, MCQ cache)
db.py               — SQLite schema, connection management, all CREATE TABLE statements
models.py           — Dataclasses (FlowCardContext, MCQCard, ConceptKnowledge, etc.)
concepts.py         — YAML loader, DAG validation, prerequisite checks
conversation.py     — Conversation engine: chat, corrections, summary, vocabulary gaps
interest.py         — Interest signal tracking, scoring, topic selection
words.py            — Word gap recording (exists, wired into flow_db.py)
bkt.py              — Bayesian Knowledge Tracing math
srs.py              — XP award calculation
lexicon.py          — Word translation lookup (used for tap-to-translate in conversations)
template_helpers.py — Jinja2 filters (markdown rendering, tappable word wrapping)
```

### Templates

```
templates/
  base.html, index.html, flow.html, concepts.html, flow_stats.html,
  flow_interests.html, lessons.html, lesson.html, decks.html, practice.html, quiz.html

templates/partials/
  flow_card.html, flow_conversation.html, flow_complete.html,
  flow_feedback.html, flow_conversation_summary.html, card_row.html
```

All templates use HTMX for dynamic content swaps + Tailwind CSS for styling. Dark theme with emerald (MCQ), violet (conversation), sky (teach) color coding.

---

## What to build next

See `BACKLOG.md` for the full ordered task list. There are two parallel tracks:

### Track A: Word-Level Tracking + New Card Types

Individual words need a lifecycle. Vocabulary should be **interest-driven** — not linear "learn all A1 words." If the user loves basketball, they should learn basketball vocabulary deeply while photography stays shallow. See DESIGN_IDEAS.md "Interest-driven vocabulary" for the full rationale.

**Word tracking:**
- `words` table: id, spanish, english, emoji, concept_id, topic_id (links to interest_topics for domain tagging), status (unseen/introduced/practicing/known), mastery_score, times_seen, times_correct
- Seed core vocabulary with emojis and topic tags. Three tiers: core (universal), functional (survival per topic), deep (interest-driven)
- Interest-driven prioritization: word intro cards surface high-interest topic words first
- Feed vocabulary_gaps into words table (partially wired already via `record_word_gap()`)

**New card types:**
- **Word intro card** — emoji + Spanish word + English translation + example sentence. Shown before a word enters practice pool.
- **Fill-in-the-blank** — Full sentence, one word blanked, 4 choices
- **Match card** — 4-5 Spanish↔English/emoji pairs, drag/tap to match
- **Sentence builder** — Scrambled words, arrange in order
- **Emoji association** — Show emoji, pick the Spanish word

### Track B: Persona System + Post-Conversation Intelligence

The conversation system is the most powerful learning tool but currently feels like an oral exam with a single persona. Transform it into something users actually want to come back to.

**Build order (each step independently useful):**

1. **Persona data layer + YAML files** — `personas` table, persona YAML files in `data/personas/` (marta, diego, abuela_rosa, luis). Each defines personality, interests, vocab level, system prompt template. New `personas.py` module to load and build prompts.

2. **Refactor conversation engine** — `conversation.py` accepts a persona object instead of hardcoded Marta. Dynamic system prompt from YAML + memory slots. Persona selection weighted by engagement (neutral start).

3. **Post-conversation evaluation (the hub)** — New `evaluation.py` module. Single LLM call after each conversation extracts:
   - Concepts demonstrated (correct/error counts) → BKT updates with boosted weight (production > recognition)
   - Vocabulary used → words table
   - User facts to remember → user_profile table
   - Persona observations → persona_memories table
   - Engagement quality signal

4. **Memory system** — `persona_memories` table (per-persona, capped ~20), `user_profile` table (shared facts). Injected into system prompts. Conversations feel personal and connected.

5. **Enjoyment scoring + persona rotation** — `persona_engagement` table tracks avg_enjoyment_score, message_length, turns, early_exit_rate per persona+topic combo. TikTok-style weighted rotation: system learns which combos work, shows more of what engages, less of what doesn't.

6. **Adaptive placement** — Placement conversation on first session that probes increasing complexity. Post-placement evaluation mass-unlocks concepts. Solves the cold start problem without boring tests. Multi-dimensional profiling: vocabulary depth per interest, grammar accuracy, conversational fluency, comprehension — tracked separately.

### Design principles

- Keep the TikTok-style infinite scroll UX — cards should feel fast and snackable
- Vocabulary follows interest, not a linear curriculum. See DESIGN_IDEAS.md for the full rationale.
- Conversations are diagnostic tools, not just practice — every conversation passively assesses the user across multiple skill dimensions
- Production evidence (using a concept in conversation) carries MORE weight than recognition (picking the right MCQ answer)
- The system should learn what the user likes without asking — infer from behavior (message length, engagement, early exit)
- Personas rotate automatically, weighted by engagement scores + novelty bonus
- New card types should work without AI where possible (match, sentence builder, emoji association)
- Card type variety should be mixed naturally into the flow, not siloed
