# Spanish Vibes — Design Ideas & Brain Dump

This file captures bigger-picture ideas that aren't ready to be backlog tasks yet. Think of it as the "thinking space" that feeds into BACKLOG.md when ideas crystallize.

---

## Persona System ("Souls")

### Core idea
Each conversation partner is a distinct character with personality, interests, memories, and a consistent voice. Not just "an AI asking questions" — someone you'd actually want to talk to.

### Implementation thinking
- Each persona gets a `soul.md` file (or YAML/JSON) defining:
  - **Name, age, location, occupation** — basic identity
  - **Personality traits** — e.g. enthusiastic, sarcastic, patient, curious
  - **Conversation style** — does this person ask lots of questions? Tell stories? Use slang? Formal vs informal?
  - **Interest levels** — predefined scores across the interest topic tree (Sports: 0.9, Music: 0.7, Politics: 0.2). This seeds what they naturally want to talk about
  - **Vocabulary level** — some personas use simpler Spanish, others push the learner
  - **Backstory** — a few sentences that give them depth and conversation hooks
- Example personas:
  - **Marta** (existing) — friendly teacher-type, patient, asks follow-up questions
  - **Diego** — football-obsessed uni student, uses slang, high energy
  - **Abuela Rosa** — warm grandmother, talks about cooking and family, uses more traditional expressions
  - **Luis** — tech startup guy, talks fast, mixes in some English loanwords

### Memory system
- **`persona_memories` table** — persona_id, memory_text, context (what conversation it came from), importance_score, created_at
- After each conversation, extract 1-2 key facts: "User said they have a dog named Max", "User mentioned they like cooking pasta", "User struggled with ser/estar for professions"
- Next conversation with same persona: inject relevant memories into the system prompt
  - "Last time you talked, Artem mentioned he has a dog named Max. You could ask about the dog."
- Keep it lightweight — maybe 10-20 memories max per persona, with importance-based pruning
- This makes repeat conversations feel personal and connected, not like starting from scratch every time

### User memories / preferences
- **`user_memories` table** — key, value, source (which conversation surfaced it), confidence, created_at
- Small fun facts: "Has a dog", "Likes Italian food", "Lives in Melbourne", "Works in tech"
- Shared across personas (they all "know" the user) but each persona reacts differently
  - Diego: "Oye, ¿cómo está Max? ¿Jugaste fútbol con él?"
  - Abuela Rosa: "¿Y tu perrito Max? ¿Le diste de comer?"
- Could also track learning preferences: "User prefers when corrections are gentle", "User likes humor in conversations"

---

## Making Conversations Actually Fun

### The problem
Current conversations feel like an oral exam — AI asks questions, user answers, AI evaluates. That's useful but not exciting.

### Research directions
- **What makes a good conversation?** Look into conversational frameworks:
  - Mutual exchange — the persona should share things about themselves too, not just interrogate
  - Humor — jokes, playful teasing, surprising responses
  - Storytelling — personas could tell short anecdotes that the user responds to
  - Disagreement/debate — light disagreements are engaging ("¿Fútbol? No, no... el baloncesto es mejor!")
  - Shared activities — "Let's order food together", "Help me plan my weekend"
- **Conversation formats beyond Q&A:**
  - Role-play scenarios (ordering at a restaurant, asking for directions, job interview)
  - Collaborative storytelling ("I start a story, you continue it")
  - Games within conversation (20 questions, would-you-rather, this-or-that)
  - Persona-driven topics (Diego won't shut up about last night's match, Abuela wants to teach you her recipe)
- **The "say it in your native language" philosophy:**
  - Already partially built (English detection → translation → vocab gap tracking)
  - Double down on this — make it feel encouraging, not penalizing
  - Persona should celebrate the attempt: "¡Ah, 'dog'! En español decimos 'perro'. ¿Tienes un perro?"
  - Build a "words I learned in conversation" feed that feels rewarding

### Engagement patterns to steal from good apps
- Cliffhangers — persona says "Te cuento algo increíble que pasó ayer..." then session ends. Next time: "¿Recuerdas lo que te iba a contar?"
- Running jokes / callbacks — built on the memory system
- Progression in relationship — early convos are more formal, later ones feel like talking to a friend
- Surprise moments — persona occasionally sends a "voice note" (TTS), shares a "photo" (emoji scene), or reacts with emotion

---

## AI Backend: LLM vs Fine-tuning vs Custom Models

### Current state
Using OpenAI API: gpt-4o-mini for MCQ generation and conversation, gpt-4o for correction evaluation.

### Options to research

**Stay with general LLMs (current approach)**
- Pros: Flexible, no training data needed, personality via system prompts, easy to iterate
- Cons: Expensive at scale, latency, personality consistency can drift, no real "memory" without RAG
- Best for: Prototyping, small user base, rapid iteration

**Fine-tuned models**
- Fine-tune a smaller model (e.g. GPT-4o-mini or Llama) on conversation transcripts that demonstrate good teaching behavior
- Pros: Cheaper inference, more consistent personality, faster responses
- Cons: Need training data (could collect from current users), less flexible, harder to iterate
- When: When you have 1000+ good conversation transcripts and costs are becoming an issue
- Could fine-tune separately per persona for distinct voices

**Hybrid approach (probably the sweet spot)**
- Use a fine-tuned small model for the bulk of conversation (fast, cheap, consistent personality)
- Use a larger model (gpt-4o) as a "supervisor" that evaluates corrections and generates memories
- System prompt + few-shot examples for personality (cheaper than fine-tuning)
- RAG for memory injection (retrieve relevant memories before each conversation)

**Self-hosted models (future)**
- Llama 3 / Mistral running on own infrastructure
- Pros: No API costs, full control, can fine-tune freely, data stays private
- Cons: Infrastructure overhead, GPU costs, smaller models may be worse at Spanish
- When: At scale (10k+ users) or when API costs are unsustainable

### Research TODOs
- [ ] Benchmark gpt-4o-mini vs gpt-4o vs Claude Haiku for conversation quality at A1-A2 level
- [ ] Test personality consistency: give same persona prompt 50 times, measure drift
- [ ] Estimate cost per user per month at current usage patterns
- [ ] Look into OpenAI fine-tuning pricing vs inference savings
- [ ] Research language learning-specific models (are there any?)
- [ ] Test Llama 3 70B for Spanish conversation quality

---

## Conversation Enjoyment Score (TikTok-style Persona Ranking)

### Core insight
You don't need to ask users which personas they like — you can infer it from how they behave in conversations. When someone's into a topic and clicks with a persona, they write more, respond faster, stay longer. When they're not, it's short answers and early exits. This is exactly how TikTok's algorithm works — watch time = interest.

### Signals (all already available in the DB, no new infrastructure needed)

**Message length (strongest signal)**
- Average words per user message in a conversation
- When you're engaged: full sentences, follow-up thoughts, questions back
- When you're bored: one-word answers, "sí", "no sé"
- Normalize per user (some people are naturally terse)

**Turn count vs max**
- Conversations have a hard cap (currently 4 turns)
- Consistently hitting the cap = engaged. Hitting "Done" after 2 = not feeling it
- Binary "did they finish?" is useful, but ratio is more nuanced

**Response time**
- Noisy on its own — fast could mean engaged OR low-effort
- Best combined with message length:
  - Fast + long = highly engaged
  - Fast + short = going through the motions
  - Slow + long = thinking carefully (good)
  - Slow + short = disengaged or struggling

**Early exit**
- Did they tap "Done" before the conversation naturally ended?
- Strong negative signal — weight heavily
- Already trackable: compare turn_count to max_turns and whether completed==1

**Corrections ratio**
- Fewer corrections might indicate comfort (or easier topic)
- Lots of corrections but kept going = motivated to learn this topic
- Lots of corrections and bailed = frustrating/too hard combo

### How to compute it

```
enjoyment_score = weighted sum of:
  - message_length_norm:  0.35  (avg words per message, normalized 0-1)
  - completion_ratio:     0.25  (turns_used / max_turns)
  - no_early_exit:        0.20  (1.0 if natural end, 0.0 if "Done" early)
  - response_time_score:  0.10  (faster = higher, but penalize if messages are short)
  - engagement_quality:   0.10  (asked questions back, used new vocab, etc.)
```

### How this feeds the recommendation engine

This creates TWO separate affinity dimensions:

1. **Topic affinity** (existing interest system) — "I like football as a subject"
2. **Persona affinity** (new) — "I enjoy talking to Diego"

The combination determines next conversation selection:
```
conversation_score = topic_affinity * 0.5 + persona_affinity * 0.3 + novelty_bonus * 0.2
```

Novelty bonus prevents the system from always picking the same persona+topic combo. Decay over time so popular combos still resurface.

### Persona rotation (answers the "should users pick?" question)

Don't let users pick — rotate automatically, weighted by engagement scores. This is the TikTok model: the algorithm learns what you like without you having to say it.

The system naturally:
- Shows more of persona+topic combos that get high enjoyment
- Shows less of low-engagement combos (but doesn't eliminate them — occasional exploration)
- Introduces new personas with a "new character" bonus to ensure they get a fair trial
- Surfaces previously-low personas occasionally to check if preferences changed

### Per-persona tracking

**`persona_engagement` table:**
- persona_id, topic_id (nullable), conversation_count, avg_enjoyment_score, avg_message_length, avg_turns, early_exit_rate, last_conversation_at
- Updated after each conversation
- Decayed over time (same half-life approach as interest system)

### Edge cases to handle
- First conversation with a new persona: give benefit of the doubt (start with neutral score, not zero)
- Topic vs persona attribution: if Diego+Football scores high, is it Diego or Football? Need some conversations with Diego+other topics to disentangle
- Struggling learner: low engagement might mean the concept is too hard, not that the persona is bad. Factor in difficulty level

---

## Adaptive Placement & Multi-Dimensional Profiling

### The problem with linear levels
Most language apps assume a single "level" and force you through content linearly. But real learners are wildly uneven. Examples:
- **Heritage speakers** (e.g. grew up hearing Russian but never studied it): native-level vocabulary and pronunciation, zero formal grammar. Grinding through "hola means hello" to get to verb conjugation is soul-crushing.
- **Classroom learners**: can conjugate every tense perfectly, freeze up in conversation, limited real-world vocabulary.
- **Immersion learners**: great conversational fluency, can get by, but full of fossilized errors and grammar gaps.
- **Mixed backgrounds**: someone who learned family/food vocab from a grandmother but nothing else.

A single "A1/A2/B1" label can't capture this. The system needs to understand that someone can be A2 vocabulary, B1 comprehension, and A1 grammar *simultaneously*.

### Skill dimensions (not a single level)

Instead of one level number, track a profile across multiple dimensions:

1. **Vocabulary depth per interest** — NOT generic "vocab breadth." Vocabulary should be shaped by what the user cares about. Someone into basketball should know cancha, anotar, triple, rebote deeply — while only having surface-level food vocab (enough to order, not discuss recipes). This is how real vocabulary works: you know the words for things you care about. Measured by: words used in conversation per topic, MCQ performance on topic-specific vocab, word intro card responses.
2. **Grammar accuracy** — Can they apply the rules? Measured by: concept mastery (existing BKT), conversation corrections (ser/estar mistakes, conjugation errors, gender agreement)
3. **Conversational fluency** — Can they produce language in real-time? Measured by: message length, response speed, willingness to form complex sentences vs sticking to safe short answers
4. **Comprehension** — Can they understand input? Measured by: do they respond appropriately to what the persona says, do they ask for clarification, listening card performance (future)

Each dimension has its own mastery curve. The system serves content that targets the weakest dimensions while not boring the learner on their strong ones.

### Interest-driven vocabulary (key design principle)

Traditional apps teach vocabulary linearly: all A1 words, then all A2 words, regardless of what you care about. This leads to the boredom problem — drilling photography vocabulary when you couldn't care less about photography.

**The Spanish Vibes approach: vocabulary follows interest.**

How it works:
- The interest system already tracks what topics the user engages with (basketball: 0.9, photography: 0.2)
- Vocabulary gets tagged by topic domain (cancha → basketball, apertura → photography)
- High-interest topics get deeper vocabulary: not just the basics but specialized words that let you have real conversations about the thing you love
- Low-interest topics get only survival vocabulary: enough to not be lost if it comes up, but no drilling
- The word intro card system prioritizes words for high-interest topics

**Virtuous cycle with conversations:**
- High interest in basketball → more basketball conversations with Diego
- Basketball conversations surface new basketball vocabulary naturally
- New words get introduced via word intro cards
- Richer vocabulary → deeper basketball conversations → more engagement → system learns you love basketball even more
- Meanwhile photography vocabulary stays shallow because you never engage with it — and that's fine

**Vocabulary tiers per topic:**
- **Core** (everyone learns): universal words needed regardless of interest — greetings, numbers, basic verbs, pronouns, question words
- **Functional** (light exposure): enough to survive a conversation about any topic — maybe 10-20 words per domain
- **Deep** (interest-driven): rich vocabulary for topics you care about — 50-100+ words, idioms, slang, nuance

The system should feel like it "gets you" — it knows you want to talk about basketball in Spanish, so it teaches you basketball words. Not because you checked a box, but because it noticed you light up when sports come up.

**Connection to personas:**
- Diego (sports) naturally teaches sports vocabulary through conversation
- Abuela Rosa (cooking/family) naturally teaches kitchen and family vocabulary
- The persona you talk to most = the vocabulary domain you go deepest in
- This means persona affinity and vocabulary depth are naturally correlated — no extra system needed, just let the conversation system do its thing

### Conversation as diagnostic (the most powerful signal)

A single conversation reveals ALL four dimensions simultaneously:
- Someone uses advanced vocabulary but butchers verb conjugation → high vocab, low grammar
- Someone writes short correct sentences but never ventures beyond simple structures → decent grammar, low fluency
- Someone responds appropriately to complex AI messages but produces simple output → high comprehension, low production

**Post-conversation LLM evaluation call** — after each conversation, one extra call to extract:
```
{
  "concepts_demonstrated": [
    {"concept_id": "ser_present", "usage_count": 3, "correct": 2, "errors": ["used ser instead of estar for location"]},
    {"concept_id": "preterite_regular", "usage_count": 1, "correct": 1, "errors": []},
    ...
  ],
  "vocabulary_used": ["nuevo", "trabajar", "cocina", ...],
  "estimated_cefr": {"vocab": "A2", "grammar": "A1", "fluency": "A2", "comprehension": "B1"},
  "notable_patterns": "User avoids subjunctive entirely. Strong food vocabulary. Consistently mixes up ser/estar."
}
```

This feeds back into the concept graph — correct spontaneous usage of a concept in conversation is STRONGER evidence of mastery than getting an MCQ right (production > recognition). The BKT update from conversation evidence should carry more weight.

### Cold start: placement without boring tests

**Option A: Placement conversation (preferred)**
- First session, before any MCQs, have a natural chat
- Persona starts simple: "¡Hola! ¿Cómo te llamas?" and gradually increases complexity
- If the user responds fluently, the persona ramps up: introduces past tense, asks more complex questions, uses harder vocabulary
- After 5-6 exchanges, run the diagnostic LLM call → instantly calibrate the entire concept graph
- Could mass-unlock concepts the user clearly already knows, skip teach cards, jump to appropriate difficulty

**Option B: Quick onboarding questions**
- "Have you studied Spanish before?" → None / A little / Intermediate / Advanced
- "Can you read this sentence?" → show progressively harder sentences
- Faster but less accurate, and less fun
- Could combine: quick questions to set a rough starting point, then placement conversation to fine-tune

**Option C: Hybrid (probably best)**
- 2-3 quick onboarding questions to avoid the worst cold-start experience
- Then immediately drop into a placement conversation that feels natural, not test-like
- System adjusts rapidly based on first few interactions
- Within 10-15 minutes of usage, the profile should be reasonably calibrated

### How this changes content selection

The card selection engine (`select_next_card()`) currently picks from buckets based on concept mastery. With dimensional profiling:
- If grammar is the weak dimension → weight toward grammar MCQs and fill-in-the-blank cards
- If vocabulary is weak but grammar is strong → more word intro cards, vocab MCQs, match cards
- If fluency is weak → more conversations, longer ones, with personas who ask open-ended questions
- If comprehension is weak → listening cards (future), reading-based MCQs, conversations where the persona uses slightly above the user's level

The system should also avoid the boredom trap: don't serve easy vocab MCQs to someone who clearly knows the words just because the concept hasn't been "officially" tested via MCQ yet. Conversation evidence should be enough to skip ahead.

### Heritage speaker / advanced beginner mode

For the specific case of someone who speaks but never studied:
- The placement conversation would quickly reveal: high vocabulary, high fluency, low grammar awareness
- System would skip ALL basic vocab content, skip teach cards for concepts they demonstrate naturally
- Focus almost entirely on grammar concepts, presented through the lens of "you already say this — here's WHY it works that way"
- MCQs would test grammar rules, not vocabulary
- Conversations would be at a comfortable level but with more grammar-focused correction

---

## Technical Architecture: How It All Connects

### The key insight: everything flows through one moment

Almost every design idea in this doc converges on a single architectural hub: the **post-conversation evaluation**. After each conversation ends, one LLM call extracts memories, assesses concepts, feeds the enjoyment score, discovers vocabulary, and updates the learner profile. Get this right and everything else plugs in.

### New modules

```
personas.py       — Load persona YAML files, build system prompts with memory injection, persona selection
evaluation.py     — Post-conversation LLM evaluation: concept assessment, memory extraction, engagement signals
words.py          — Word lifecycle management (already emerging from backlog work)
```

Existing modules that change:
```
conversation.py   — Refactor to accept persona object instead of hardcoded Marta. Core chat loop stays the same.
flow.py           — select_next_card() gains persona+topic selection for conversations, word intro card injection
flow_db.py        — New tables: personas, persona_memories, user_profile, persona_engagement, words
interest.py       — Persona engagement tracking bolted on alongside existing topic interest
```

### New DB tables

```sql
-- Persona registry (actual personality in YAML files, not DB)
CREATE TABLE personas (
    id TEXT PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    soul_file_path TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- What each persona remembers from past conversations
CREATE TABLE persona_memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    persona_id TEXT NOT NULL REFERENCES personas(id),
    memory_text TEXT NOT NULL,
    conversation_id INTEGER REFERENCES flow_conversations(id),
    importance_score REAL NOT NULL DEFAULT 0.5,
    created_at TEXT NOT NULL
);

-- Facts about the user, shared across all personas
CREATE TABLE user_profile (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    source_conversation_id INTEGER,
    confidence REAL NOT NULL DEFAULT 0.5,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Engagement tracking per persona+topic combo
CREATE TABLE persona_engagement (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    persona_id TEXT NOT NULL REFERENCES personas(id),
    topic_id INTEGER REFERENCES interest_topics(id),
    conversation_count INTEGER NOT NULL DEFAULT 0,
    avg_enjoyment_score REAL NOT NULL DEFAULT 0.5,
    avg_message_length REAL NOT NULL DEFAULT 0.0,
    avg_turns REAL NOT NULL DEFAULT 0.0,
    early_exit_rate REAL NOT NULL DEFAULT 0.0,
    last_conversation_at TEXT,
    UNIQUE(persona_id, topic_id)
);

-- Words table (from backlog, with topic tagging for interest-driven vocab)
CREATE TABLE words (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    spanish TEXT NOT NULL,
    english TEXT NOT NULL,
    emoji TEXT,
    concept_id TEXT REFERENCES concepts(id),
    topic_id INTEGER REFERENCES interest_topics(id),
    status TEXT NOT NULL DEFAULT 'unseen',  -- unseen/introduced/practicing/known
    mastery_score REAL NOT NULL DEFAULT 0.0,
    times_seen INTEGER NOT NULL DEFAULT 0,
    times_correct INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(spanish, english)
);
CREATE INDEX idx_words_topic ON words(topic_id);
CREATE INDEX idx_words_concept ON words(concept_id);
CREATE INDEX idx_words_status ON words(status);
```

### Persona YAML file structure

Files live in `data/personas/`. Example `diego.yaml`:

```yaml
id: diego
name: Diego
age: 22
location: Madrid
occupation: University student
personality:
  traits: [enthusiastic, competitive, funny, impatient]
  formality: informal
  humor: high
  patience: medium
interests:
  sports: 0.95
  football: 0.99
  gaming: 0.7
  music: 0.6
  food_cooking: 0.3
  photography: 0.1
vocab_level: casual_a2    # Uses slang, contractions, informal tú
backstory: |
  Diego is a 22-year-old sports science student in Madrid.
  He's obsessed with football and plays for his university team.
  He uses a lot of slang and speaks fast. He's friendly but
  competitive — he'll challenge you to know football vocabulary.
system_prompt_template: |
  You are Diego, a 22-year-old university student from Madrid.
  You're enthusiastic, funny, and a bit impatient. You LOVE football
  and sports. You use informal tú, slang, and speak naturally.
  You share your own opinions and stories — don't just ask questions.
  You sometimes tease the learner playfully when they make mistakes.

  {persona_memories}
  {user_profile}
  {concept_focus}
```

### Post-conversation evaluation flow

```
Conversation ends
       │
       ▼
evaluation.py: evaluate_conversation(messages, persona, topic, concept_id)
       │
       │  Single LLM call → structured JSON response
       │
       ├──► concepts_demonstrated → update_concept_knowledge() with boosted weight
       ├──► vocabulary_used → upsert into words table, mark as "practicing"
       ├──► user_facts → upsert into user_profile table
       ├──► persona_observations → insert into persona_memories (with importance scoring)
       ├──► engagement_quality → combine with local signals → enjoyment_score
       │        │
       │        ▼
       │    update persona_engagement table
       │
       └──► estimated_cefr_dimensions → update dimensional profile
                                        (used by card selection for content targeting)
```

### Conversation selection algorithm

When `select_next_card()` decides it's time for a conversation:

```
For each possible (persona, topic) combo:
    score = (
        topic_affinity * 0.40          # from existing interest system
      + persona_affinity * 0.30        # from persona_engagement.avg_enjoyment_score
      + novelty_bonus * 0.20           # higher if this combo hasn't been used recently
      + concept_alignment * 0.10       # does this persona naturally teach concepts the user needs?
    )

Pick top-scoring combo (with some randomness to explore)
Load persona YAML → build system prompt with memories → start conversation
```

### Build order (dependency chain)

Each step is independently useful. You can ship after any step.

1. **Persona files + loader** — Just data + a YAML reader. No DB changes yet. Test by loading files.
2. **Refactor conversation engine** — Accept persona object, build dynamic prompts. Conversations immediately get personality variety.
3. **Post-conversation evaluation** — The hub. One new LLM call, structured extraction. Even without memory/engagement tables, this gives you concept assessment from conversations.
4. **Memory tables + injection** — persona_memories, user_profile. Conversations start feeling personal and connected.
5. **Enjoyment scoring + persona rotation** — persona_engagement table, TikTok-style weighted selection. System learns which persona+topic combos work.
6. **Word tracking + interest-driven vocab** — words table, word intro cards, topic-tagged vocabulary. Vocabulary follows interest.
7. **Placement conversation** — Special onboarding mode. Cold start solved.

## Accelerating Word Tracking (The "15 Words" Problem)

### The bottleneck
The words dashboard shows only ~15 tracked words. That's because words only enter the system two ways: 16 seed words and vocabulary gaps from English fallback during conversations. The pipeline is way too narrow — you'd need to fall back to English dozens of times to build up a reasonable word list. Meanwhile every Spanish word the user produces successfully in conversation goes completely untracked.

### Three fixes that stack together

**1. Harvest from conversations**
After every conversation ends, extract all meaningful Spanish words the user produced. These words skip the intro card entirely — if you produced it correctly in conversation, you already know it. They enter as 'practicing' (production evidence > recognition). Stop words and articles are excluded.

This is the single biggest change. A 4-turn conversation might surface 20-40 unique Spanish words. Instead of tracking 2-3 words per session (from English fallback), we'd track dozens.

For existing words, conversation usage should boost times_seen AND times_correct — they used it correctly in context, which is stronger evidence than an MCQ.

**2. Track word taps**
When a user taps a word during conversation to see its translation, that's a signal. Every tap gets recorded to a `word_taps` table (full history, not upserted — we want to see repeated lookups). The tapped word also gets added to the words table if it's not already there.

Tap signals feed into the system in two ways:
- **Repeated taps** = "I don't know this word" → promote it for teaching (generate practice cards for it)
- **Single tap** = "I'm curious about this word" → track it, but lower priority

Tapped words enter as 'unseen' (unlike conversation-produced words which enter as 'practicing') — the user looked it up because they didn't know it, so they still need to learn it.

**3. Smart word introductions (beginner vs intermediate)**
The intro card system needs to be level-aware:

- **Beginners** — Interest-driven vocab doesn't make sense yet. You need mesa, silla, comer, beber — the survival stuff. Push core vocabulary (greetings, numbers, basic verbs, everyday objects, food) regardless of interest. Interest only kicks in once you've got the foundation (~50-100 core words known).

- **Intermediate+** — Once someone's producing words in conversation, the system should back off on introductions. Don't intro words they already demonstrated knowing. Focus intro cards on: (a) words they tapped (they asked to learn these!), (b) words from high-interest topics they haven't encountered yet, (c) words that would unlock richer conversations with their favorite personas.

- **Don't intro every word** — It's not realistic to intro-card every word. The system should be selective: intro core vocab for beginners, tapped words for everyone, and interest-driven deep vocab for engaged learners. Most words should enter the system organically through conversation harvesting and just be tracked, not formally introduced.

### How this changes the word lifecycle

Current: `seed (16 words) → unseen → [wait for intro card] → introduced → practicing → known`

New, multiple entry points:
- **Seed words** → unseen → intro card → practicing → known (beginners only)
- **Conversation production** → practicing (skip intro!) → known
- **Word tap** → unseen → [prioritized for intro/practice card] → practicing → known
- **English fallback gap** → unseen → [existing pipeline] → practicing → known
- **Tapped + repeated** → unseen → [high-priority intro card generated] → practicing → known

---

## Conversation Types

### The problem with one-size-fits-all conversations
If every conversation is the same format — persona asks questions, user answers, free-form chat — there's no structural variety. Worse, the system can't distinguish "doesn't know subjunctive" from "wasn't pushed to use subjunctive." Different conversation types solve both problems: they keep things fresh AND create opportunities to diagnose specific skills.

### The four types

**1. Role Play**
- Scenario-based: ordering at a restaurant, asking for directions, job interview, buying a gift, calling a doctor
- Persona plays a role (waiter, stranger on the street, interviewer) and the user plays themselves
- Natural way to surface domain-specific vocabulary and common phrases
- Can target specific situations the user might actually encounter
- Good for: fluency, real-world vocabulary, comprehension

**2. General Chat**
- Free-form conversation, no particular goal
- Persona talks about whatever they're interested in, user goes wherever they want
- This is the default/baseline — the "hanging out with a friend" mode
- Best for: building comfort, discovering interests, long-term engagement
- Also the best mode for memory building — casual chat reveals personal facts

**3. Tutor Mode**
- Persona explicitly teaches or helps with a specific concept
- "Hoy te voy a enseñar cuándo usar ser y cuándo usar estar" — then walks through examples, asks the user to try, corrects gently
- NOT a lecture — still conversational, but with a clear teaching goal
- Good for: grammar concepts the user is struggling with, filling specific gaps
- The persona's personality still shines through (Diego teaches with football examples, Abuela teaches with cooking)

**4. Concept-Required ("Use It or Lose It")**
- The system picks 1-2 specific concepts the user needs to practice
- The conversation is otherwise free-form, BUT the user is nudged to use those concepts
- Example: concept = preterite tense → persona steers toward "¿Qué hiciste ayer?" territory
- At the end, evaluation checks: did the user actually produce the target concept?
- Pass/fail assessment — stronger evidence than MCQs because it's spontaneous production
- Directly solves the "avoided structure" problem: if the system suspects someone avoids subjunctive, queue up a concept-required conversation targeting subjunctive

### How types get selected

Not every conversation should be the same type. The mix depends on the learner's state:

- **Default rotation**: ~50% general chat, ~20% role play, ~15% concept-required, ~15% tutor
- **If a concept is stuck** (high MCQ recognition but never used in conversation): bump concept-required frequency for that concept
- **If a concept just introduced**: schedule a tutor-mode conversation soon after teach cards
- **If engagement is dropping**: more general chat and role play (the fun ones), fewer tutor sessions
- **If the user is advanced**: less tutor mode (they don't need hand-holding), more role play with complex scenarios

The conversation type feeds into the system prompt for the persona:
```yaml
# In the system prompt template:
{conversation_type_instruction}

# Which resolves to something like:
# Role play: "You are a waiter at a tapas restaurant in Barcelona. The user is a customer ordering dinner."
# General chat: "Have a natural conversation. Talk about whatever interests you both."
# Tutor: "Today you're helping the user understand [concept]. Teach through examples and practice, not lectures."
# Concept-required: "Have a natural conversation, but steer it so the user needs to use [concept]. Don't tell them what to practice — just create situations where it's needed."
```

### Evaluation differs by type

The post-conversation evaluation call should know the conversation type:
- **General chat**: extract memories, assess whatever concepts appeared naturally
- **Role play**: assess vocabulary used, scenario completion, appropriate register
- **Tutor**: did the user demonstrate understanding of the target concept by the end?
- **Concept-required**: binary — did the user produce the target concept(s)? How accurately? This is the strongest evidence for mastery (or lack thereof)

---

## Story Comprehension Card

### The idea
The persona tells a short story in Spanish (3-5 sentences), then the user gets quizzed on it. "¿Quién fue al mercado?" / "¿Qué compró María?" — simple comprehension questions. Tests listening/reading comprehension without requiring production.

### Why this is powerful
- It's a **fifth conversation type** that fits naturally alongside role play, general chat, tutor, and concept-required
- Tests comprehension directly — the one dimension that's hardest to assess in free-form conversation
- The persona's personality flavors the story (Diego tells about a football match, Abuela tells about cooking mishaps, Luis tells about a startup pitch gone wrong)
- Stories naturally contain target grammar in context — preterite for "what happened" stories, imperfect for "when I was young" stories
- Low pressure — user just answers questions, doesn't have to produce Spanish (good for beginners or variety)
- Can scale difficulty: A1 stories are 2-3 simple sentences with yes/no questions, A2 stories are longer with open-ended questions

### How it could work
1. System selects a concept + persona + topic
2. LLM generates a short story (3-5 sentences) using the target grammar, in the persona's voice
3. Story is displayed with tappable words (existing infrastructure)
4. After reading, 2-3 comprehension MCQs appear:
   - Factual: "¿Adónde fue Diego?" (where did Diego go?)
   - Inference: "¿Por qué estaba triste María?" (why was María sad?)
   - Grammar-focused: "¿Qué tiempo verbal usa la historia?" (what tense does the story use?) — optional, more meta
5. Answers feed into concept mastery (comprehension evidence) and word tracking (words in the story)

### Variations
- **Retell mode** (harder): after the quiz, ask the user to retell the story in their own words — now it's production evidence too
- **Fill-in-the-story**: story with blanks, user picks the right word — bridges comprehension and vocabulary
- **Continuing the story**: persona starts, user adds the next sentence — collaborative storytelling from the earlier design ideas

---

## Open Questions

- How many personas is the right number to start with? 3-4 feels right — enough variety without too much to maintain
- Should personas unlock as the user progresses? (Abuela Rosa at A1, Diego at A2 when you can handle slang?)
- How to handle memory conflicts? (User tells Marta they're vegetarian, then tells Diego they love steak)
- How much of the persona's personality should come from the system prompt vs fine-tuning vs few-shot examples?
- For enjoyment scoring: how many conversations needed before the signal is reliable? Probably 3-5 per persona minimum
- Should users ever see their persona affinity scores? Could be a fun "your Spanish friends" dashboard
- For the post-conversation diagnostic call: how expensive is this per conversation? Can it be folded into the existing correction/summary call?
- How aggressively should the system skip content based on conversation evidence? Too aggressive = gaps, too conservative = boredom
- Should the dimensional profile be visible to the user? A radar chart showing vocab/grammar/fluency/comprehension could be motivating
- ~~How to handle the "avoided structure" signal~~ → Solved by "Concept-Required" conversation type (see Conversation Types section). If someone never uses subjunctive, schedule a concept-required conversation that forces it. If they still can't produce it, that's a clear signal.
