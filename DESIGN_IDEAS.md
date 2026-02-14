# Spanish Vibes — Design Ideas & Architecture

This file captures the design thinking behind Spanish Vibes. Sections marked ✅ are implemented. Sections marked 💡 are ideas not yet built.

---

## ✅ Persona System ("Souls")

### What's built
Each conversation partner is a distinct character with personality, interests, memories, and a consistent voice. Four personas live in `data/personas/` as YAML soul files:

- **Marta** — friendly teacher-type, patient, asks follow-up questions
- **Diego** — football-obsessed uni student, uses slang, high energy
- **Abuela Rosa** — warm grandmother, talks about cooking and family, traditional expressions
- **Luis** — tech startup guy, talks fast, mixes in English loanwords

Each YAML defines identity, personality traits, conversation style, interest weights, vocab level, backstory, and a system prompt template with injection slots for `{persona_memories}`, `{user_profile}`, and `{concept_focus}`.

### How it works
- `personas.py` loads YAML files, builds dynamic system prompts with memory injection
- `select_persona()` uses engagement-weighted random selection — personas with higher enjoyment scores get picked more often, with a novelty bonus for less-seen personas
- `get_persona_prompt()` injects retrieved memories and user facts into the system prompt before each conversation
- Conversations reference a persona_id, so the system knows who said what

### 💡 Future ideas
- **More personas** — A sarcastic teenager, a professor type, a traveler. Each unlocks naturally as the system learns what the user responds to
- **Persona unlocking** — Could gate some personas behind level thresholds (Diego's slang is hard for A1 learners)
- **Voice differentiation** — If/when TTS is added, each persona gets a distinct voice style
- **"Your Spanish friends" dashboard** — Show persona affinity scores, conversation count per persona, fun stats

---

## ✅ Memory System

### What's built
Two complementary memory stores:

**Persona memories** (`persona_memories` table) — What each persona remembers from past conversations. Capped at ~20 per persona, pruned by importance + recency. Examples: "User mentioned they have a dog named Max", "User struggled with ser/estar for locations."

**User profile** (`user_profile` table) — Facts about the user, shared across all personas. Key-value pairs with confidence scores. Examples: "Has a dog", "Likes Italian food", "Lives in Melbourne."

Both are extracted via the post-conversation evaluation LLM call and injected into persona system prompts before each new conversation.

### 💡 Future ideas
- **Memory conflicts** — What happens when the user tells Marta they're vegetarian but tells Diego they love steak? Could be handled with confidence decay or explicit contradiction detection
- **Learning preference tracking** — "User prefers gentle corrections", "User likes humor in conversations"
- **Memory-driven conversation starters** — Persona opens with a callback: "¿Cómo está Max?" instead of generic greetings

---

## ✅ Making Conversations Fun

### What's built

**Conversation types** — Six distinct modes, not just free-form Q&A:

1. **General chat** (~50%) — Free-form, persona-driven. Best for building rapport and discovering interests
2. **Role play** (~20%) — Scenario-based (ordering food, asking directions, job interview). Curated scenarios per topic
3. **Concept-required** (~15%) — System picks concepts the user needs to practice, steers conversation to require them. Binary pass/fail on target concept production
4. **Tutor** (~15%) — Persona explicitly teaches a concept, with their personality flavoring the examples
5. **Story comprehension** — Persona tells a short story, user answers comprehension questions (UI scaffolding exists, generation logic TBD)
6. **Placement** — Special onboarding mode for calibrating new users

Type selection is weighted and adapts: if a concept is stuck, bump concept-required frequency. If engagement drops, more fun types (chat, role play).

**Enjoyment scoring** — TikTok-style behavioral inference, no explicit feedback needed:
```
enjoyment_score = weighted sum of:
  message_length_norm:  0.35
  completion_ratio:     0.25
  no_early_exit:        0.20
  response_time_score:  0.10
  engagement_quality:   0.10  (from LLM evaluation)
```

**Persona engagement tracking** (`persona_engagement` table) — Per persona×topic: conversation count, average enjoyment, average message length, average turns, early exit rate. Feeds into persona selection weighting.

### 💡 Future ideas
- **Running jokes / callbacks** — Built on memory system. Persona references something funny from a past conversation
- **Progression in relationship** — Early convos more formal, later ones feel like talking to a friend
- **Cliffhangers** — "Te cuento algo increíble..." then session ends. Next time picks up the thread
- **Collaborative storytelling** — "I start a story, you continue it" mode
- **Games within conversation** — 20 questions, would-you-rather, this-or-that
- **Mutual exchange** — Persona shares opinions and stories proactively, not just asking questions

---

## ✅ Post-Conversation Evaluation (The Hub)

### What's built

The architectural insight from the original design proved correct: almost everything flows through one moment — the post-conversation evaluation. After each conversation, a single GPT-4o call extracts:

```json
{
  "concepts_demonstrated": [{"concept_id": "ser_present", "correct": 2, "errors": [...]}],
  "vocabulary_used": ["nuevo", "trabajar", "cocina"],
  "user_facts": ["Has a dog named Max"],
  "persona_observations": ["User seemed excited about football"],
  "engagement_quality": 0.75,
  "estimated_cefr": "A2"
}
```

This feeds: BKT updates (with boosted weight for production evidence), word harvesting, memory storage, persona engagement tracking, interest signals, and enjoyment scoring. One call, six downstream systems.

---

## ✅ Adaptive Difficulty & Placement

### What's built

**Computed user level** — `get_user_level()` in `flow.py` computes a global level from BKT concept mastery across tiers:
- Tier 1 mastery < 50% → level 1, CEFR A1
- Tier 1 ≥ 80%, Tier 2 < 50% → level 2, CEFR A1-A2
- Tier 2 ≥ 80% → level 3, CEFR A2-B1

This drives MCQ difficulty-aware selection and conversation scaffolding (CEFR level in system prompts).

**Placement conversation** — Special onboarding flow: 2-3 quick interest questions → placement conversation where persona probes increasing complexity → post-placement evaluation mass-unlocks concepts the user already knows.

### 💡 Multi-Dimensional Profiling (Not Yet Built)

The current system uses a single global level. The original design called for tracking four independent dimensions:

1. **Vocabulary depth per interest** — You might know 100 sports words but only 10 food words. Vocabulary shaped by what you care about.
2. **Grammar accuracy** — BKT mastery + conversation correction patterns
3. **Conversational fluency** — Message length, response speed, sentence complexity
4. **Comprehension** — Can they understand input? Appropriate responses, clarification requests

Each dimension would have its own mastery curve. Content selection would target the weakest dimension while not boring the learner on strong ones.

**Heritage speaker mode** — For someone who speaks but never studied: high vocabulary + high fluency + low grammar awareness. System would skip all basic vocab, focus entirely on grammar through the lens of "you already say this — here's WHY it works."

This is the most ambitious unrealized idea. The infrastructure is mostly there (evaluation already extracts concepts, vocabulary, engagement quality), but the card selection engine doesn't yet differentiate by dimension.

---

## ✅ Interest System

### What's built

**Interest tracking** — Exponential moving average scoring with signal weighting:
- Correctness: 0.40, Dwell time: 0.30, Return frequency: 0.15, Progression: 0.10, Continuation: 0.05
- Struggle detection: long dwell + wrong answer = don't boost (prevents false positives from frustration)
- Time decay: 45-day half-life (interests fade without interaction)

**21 interest topics** seeded: Sports, Football, Technology, Music, Food & Cooking, Travel, Movies & TV, Science, Politics & News, Fashion, Gaming, Fitness, Business, Art, History, Nature & Animals, Relationships, Literature, Health, Cars, Photography.

**Signal source design** — Conversations produce interest signals (they reflect genuine engagement). MCQs consume interests (word/topic selection) but don't produce signals (they're assigned, not chosen).

**Concept-to-topic mapping** — `CONCEPT_TOPIC_MAP` in `interest.py` links 15 concepts to topic slugs (food_vocab→food-cooking, animals_vocab→nature-animals, etc.).

### 💡 Future ideas
- **Deeper topic hierarchy** — Football under Sports, Italian food under Food & Cooking. Lets the system get more specific over time
- **Cross-persona interest triangulation** — If the user loves sports with Diego AND loves sports with Marta, that's stronger signal than just one persona
- **Interest-driven conversation topics** — Already partially wired, but could be more aggressive about surfacing topics the user loves

---

## ✅ Word System

### What's built

**531 seed words** across all 61 concepts in `data/seed_words.json`. Words have Spanish, English, emoji, example sentence, concept_id, and topic_slug for interest-driven prioritization.

**Word lifecycle** — Multiple entry points:
- **Seed words** → unseen → intro card → introduced → practice card → known (2 correct = known)
- **Conversation production** → practicing (skip intro! production > recognition) → known
- **Word tap** (lookup during conversation) → unseen → prioritized for intro/practice → known
- **English fallback gap** → unseen → existing pipeline → known

**Interest-aware selection** — `get_intro_candidate_weighted()` prefers unseen words from high-interest topics. If the user loves sports, sports vocabulary surfaces before photography vocabulary.

**Translation pipeline** — 3-tier fallback: word_translations cache → bundled es_en_dictionary.json (~5000 entries) → GPT-4o-mini AI translation.

**Conversation harvesting** — After each conversation, all meaningful Spanish words the user produced are extracted, stop words filtered, and added to the words table. Existing words get times_correct bumped (production evidence).

**Word tap tracking** — Every tap recorded in `word_taps` table with full audit trail. Tapped words enter as 'unseen' (they looked it up because they don't know it).

### 💡 Interest-Driven Vocabulary (The Virtuous Cycle)

The big design vision for vocabulary that's partially wired but not fully realized:

**The cycle:**
- High interest in basketball → more basketball conversations with Diego
- Basketball conversations surface new basketball vocabulary naturally
- New words get introduced via word intro cards (interest-weighted)
- Richer vocabulary → deeper basketball conversations → more engagement → system learns you love basketball even more
- Meanwhile photography vocabulary stays shallow because you never engage with it — and that's fine

**Vocabulary tiers per topic:**
- **Core** (everyone learns): universal words — greetings, numbers, basic verbs, pronouns, question words. topic_slug = null
- **Functional** (light exposure): enough to survive any topic — 10-20 words per domain
- **Deep** (interest-driven): rich vocabulary for topics you care about — 50-100+ words, idioms, slang

**What's still needed:**
- **Word-aware MCQ generation** — Tell the AI which words the user knows so distractors use known vocabulary
- **More aggressive interest weighting** — Current system just prefers high-interest words within a concept. Could go further: choose which CONCEPT to drill based on interest alignment
- **Deep vocabulary seeding** — Current 531 words are functional-level. For deep engagement with a topic, need specialized vocabulary beyond what's in concept teach_content

---

## 💡 New Card Types

### Built
- **Teach card** — Concept introduction with formatted content
- **MCQ** — AI-generated multiple choice, difficulty 1-3
- **Word intro** — Show a new word with emoji, translation, example
- **Word practice** — Fill-in-the-blank with word
- **Word match** — Match Spanish-English pairs
- **Conversation** — Full chat with persona (6 types)

### Not yet built
- **Story comprehension** — Persona tells a short story (3-5 sentences) using target grammar, then 2-3 comprehension MCQs. UI scaffolding exists in templates, needs generation logic. Variations: retell mode, fill-in-the-story, continuing the story.
- **Fill-in-the-blank** — Full sentence with one word blanked, 4 choices. Context constrains the answer. Different from MCQ because it's inline and tests reading comprehension in context.
- **Sentence builder** — Scrambled words, arrange in correct order. Tests word order / grammar understanding differently.
- **Listening card** (future) — Play a sentence via TTS, pick the translation or type what you heard. Browser SpeechSynthesis API is free.
- **Image/emoji association** — Show an emoji or simple image, pick the Spanish word. Fast, visual, low-stakes.

---

## 💡 AI Backend: Future Considerations

### Current state
- **GPT-4o** for conversation corrections and post-conversation evaluation
- **GPT-4o-mini** for MCQ generation, conversation chat, word translation fallback
- Works well for prototyping and small user base

### Future options when scaling
- **Fine-tuned small models** per persona — cheaper inference, more consistent personality. Need 1000+ conversation transcripts
- **Hybrid** — small model for chat, large model for evaluation/memory extraction
- **Self-hosted** (Llama/Mistral) — no API costs at scale, full control, but infrastructure overhead
- **Cost optimization** — batch evaluation calls, cache common translations, reduce MCQ regeneration

---

## ✅ Technical Architecture

### The system as built

```
data/
  concepts.yaml          — 61 concepts across 8 tiers (A1→A2)
  seed_words.json        — 531 words with emoji, examples, topic tags
  personas/*.yaml        — 4 persona soul files
  es_en_dictionary.json  — ~5000 Spanish-English translations

src/spanish_vibes/
  flow.py               — Card selection engine (teach → word_intro → word_match → word_practice → MCQ → conversation)
  flow_routes.py        — HTTP endpoints, card serving, conversation management
  flow_ai.py            — MCQ generation via GPT-4o-mini
  flow_db.py            — Flow session DB queries
  conversation.py       — Chat engine, CEFR scaffolding, concept steering
  personas.py           — YAML loading, prompt building, engagement-weighted selection
  evaluation.py         — Post-conversation GPT-4o evaluation + enjoyment scoring
  memory.py             — Store/retrieve persona memories + user profile
  interest.py           — EMA interest scoring, topic matching, decay
  words.py              — Word lifecycle, seeding, harvesting, intro/practice/match cards
  lexicon.py            — Translation pipeline (cache → dictionary → AI)
  concepts.py           — Concept loading, topological sort, prerequisite checking
  bkt.py                — Bayesian Knowledge Tracing (P_L0=0.0, P_T=0.1, P_G=0.25, P_S=0.1)
  srs.py                — XP-based level (decorative)
  conversation_types.py — 6 conversation types with weighted selection
  db.py                 — SQLite schema, migrations, 30+ tables
```

### Data flow

```
User starts session
       │
       ▼
select_next_card() in flow.py
       │
       ├── Concept selection: weighted buckets (spot 30%, practice 50%, new 20%)
       ├── Card type cascade: teach → word_intro → word_match → word_practice → MCQ
       ├── Conversation trigger: every 5th card if experienced
       │
       ▼
Card served → User responds
       │
       ├── MCQ answer → BKT update + CardSignal (topic_id=None)
       ├── Word intro → mark_word_introduced()
       ├── Word practice → mark_word_practice_result()
       │
       └── Conversation ends
               │
               ▼
        Post-conversation evaluation (GPT-4o)
               │
               ├── concepts_demonstrated → BKT update (boosted weight)
               ├── vocabulary_used → harvest_conversation_words()
               ├── user_facts → store in user_profile
               ├── persona_observations → store in persona_memories
               ├── engagement_quality → enjoyment_score → persona_engagement
               └── interest signal → InterestTracker.update_from_card_signal()
```

---

## 💡 Open Questions

- Should the dimensional profile (vocab/grammar/fluency/comprehension) be visible to users? A radar chart could be motivating
- How aggressively should conversation evidence skip content? Too aggressive = gaps, too conservative = boredom
- How many conversations before persona engagement signal is reliable? Probably 3-5 per persona minimum
- For story comprehension: should the story be generated per-conversation or pre-cached?
- When does interest-driven vocabulary become counterproductive? (User only learns sports words, can't have a basic conversation about anything else)
- How to handle the transition from core vocabulary (everyone needs it) to interest-driven vocabulary (personalized)?
