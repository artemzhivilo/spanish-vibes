# Spanish Vibes Engine Overview

A complete map of how the engine works, what's built, what's not, and where to improve.

---

## How a Card Gets Selected

When you open `/flow`, here's exactly what happens:

```
GET /flow
  → start_or_resume_session()
  → render flow.html (HTMX loads first card)

GET /flow/card?session_id=X
  → select_next_card(session_id)     ← THIS IS THE CORE ENGINE
```

### select_next_card() — Step by Step

**1. Classify all concepts into buckets:**
- **Mastered** (p_mastery ≥ 0.90 AND ≥ 5 attempts) → spot-check bucket
- **Learning** (any attempts but not mastered) → practice bucket
- **New** (0 attempts, all prerequisites met) → new bucket

**2. Pick which bucket to draw from (weighted random):**
- Spot-check (mastered): **30%**
- Practice (learning): **50%**
- New: **20%**
- Within learning bucket: biased toward lowest p_mastery (weakest first)
- All tunable via dev overrides

**3. Pick a concept from the chosen bucket**

**4. Decide card type (priority order):**

| Priority | Card Type | When |
|----------|-----------|------|
| 1 | Dev forced | `force_next_card_type` override is set |
| 2 | Conversation | Every 5 cards (tunable), IF concept has 3+ attempts AND AI available |
| 3 | Teach | New concept, teach card not yet shown |
| 4 | Word intro | Unseen word available for this concept |
| 5 | Word match | 40% chance (if words available) |
| 6 | Word practice | 60% chance (if words available) |
| 7 | MCQ | Default fallback — AI-generated, cached in batches of 15 |

**5. Build FlowCardContext and render the appropriate template**

---

## BKT (Bayesian Knowledge Tracing) — How Concepts Level Up

Each concept has a `p_mastery` score (0.0 to 1.0) representing probability the learner knows it.

### The Math
```
After correct answer:
  posterior = p_mastery × (1 - slip) / [p_mastery × (1 - slip) + (1 - p_mastery) × guess]

After wrong answer:
  posterior = p_mastery × slip / [p_mastery × slip + (1 - p_mastery) × (1 - guess)]

Then: p_new = posterior + (1 - posterior) × learn_rate
```

### Parameters
| Param | Value | Meaning |
|-------|-------|---------|
| P_L0 (prior) | 0.0 | Start knowing nothing |
| P_T (learn rate) | 0.1 | 10% learning per attempt |
| P_G (guess rate) | 0.25 | 1-in-4 chance of guessing right (MCQ) |
| P_S (slip rate) | 0.1 | 10% chance of slipping on known material |
| Mastery threshold | 0.90 | Need 90% confidence to master |
| Min attempts | 5 | At least 5 attempts before mastery |

### Concept Prerequisite System
- Concepts form a DAG (directed acyclic graph)
- A concept unlocks when ALL its prerequisites are mastered
- `get_next_new_concepts()` returns up to 3 unlocked concepts at a time

---

## Persona System

### How Persona Selection Works
```
For each persona:
  score = engagement_affinity × 0.6
        + novelty_bonus × 0.3
        + random_explore × 0.1

Pick using weighted random from scores.
Exclude the persona used in the last conversation (anti-repeat).
```

- **engagement_affinity**: running average enjoyment score from past conversations (default 0.5)
- **novelty_bonus**: `min(1.0, days_since_last_conversation / 5.0)` — max bonus if unused 5+ days
- **random_explore**: pure randomness for exploration

### What's Built
- Weighted selection algorithm ✅
- Engagement tracking table ✅
- Novelty bonus calculation ✅
- YAML loader for persona files ✅

### What's Missing
- **No persona YAML files exist** → always falls back to hardcoded Marta
- **No persona memories** → conversations don't carry over
- **No user profile** → facts shared across personas not tracked

---

## Conversation System

### Lifecycle
```
1. START
   → select_persona() picks who you talk to
   → get_type_instruction() builds type-specific system prompt
   → generate_opener() — first AI message
   → Insert into flow_conversations table

2. PER-TURN (up to 4 turns)
   → User types message
   → respond_to_user() — single LLM call that:
     - Checks grammar
     - Generates corrected recast woven into reply
     - Continues conversation naturally
   → Returns: {reply, corrections, steering}

3. END (user clicks "Done" or 4 turns reached)
   → evaluate_conversation() — single LLM call extracts:
     - concepts_demonstrated (with correct/error counts)
     - vocabulary_used
     - user_facts
     - persona_observations
     - engagement_quality (0-1)
     - estimated_cefr
   → compute_enjoyment_score()
   → update_persona_engagement()
   → Update BKT from conversation evidence
   → Harvest words from conversation
```

### Conversation Types
| Type | Weight | Description |
|------|--------|-------------|
| general_chat | 45% | Free-form mutual exchange |
| role_play | 20% | Scenario-based (waiter, tour guide, etc.) |
| concept_required | 15% | Steers conversation to force target grammar |
| tutor | 10% | Explicit teaching + practice |
| story_comprehension | 10% | Persona tells story, user answers MCQs |

### Enjoyment Score (computed after each conversation)
```
message_length_norm   × 0.35
+ completion_ratio    × 0.25
+ no_early_exit       × 0.20
+ response_time_score × 0.10
+ engagement_quality  × 0.10
```

---

## Word Tracking

### How Words Enter the System
1. **Seed words** — 16 hardcoded basics (greetings, numbers, colors, food)
2. **Conversation harvesting** — extracted from user's Spanish messages after conversation ends
3. **Word taps** — recorded when user clicks a word to translate during conversation
4. **English fallback gaps** — recorded when user types English instead of Spanish

### Word Lifecycle
```
unseen → introduced (via word_intro card) → practicing (via word_practice/match) → known
```

Conversation-produced words can skip intro and enter as "practicing" (production evidence).

### What's Built
- Seed words ✅
- Word intro/practice/match cards ✅
- Word tap recording ✅
- Basic conversation harvesting ✅

### What's Weak
- Only ~16 seed words in the system
- Tap data collected but not used for prioritization
- No spaced repetition for individual words
- No interest-driven word selection

---

## Interest Tracking

Fully built system that tracks what topics engage the learner.

### Signal Weights
| Signal | Weight | What it measures |
|--------|--------|-----------------|
| Correctness | 0.40 | Getting answers right on topic |
| Dwell time | 0.30 | Time spent on cards (sweet spot ~30s) |
| Return frequency | 0.15 | Coming back to same topic |
| Progression | 0.10 | Improving over time |
| Continuation | 0.05 | Not quitting after topic cards |

Interest topics are passed to card context for theming conversations and MCQs.

---

## What's Fully Working

| System | Status | Notes |
|--------|--------|-------|
| BKT + Concepts | ✅ Complete | Full prerequisite DAG, mastery tracking |
| MCQ Generation | ✅ Complete | AI-generated, cached in batches of 15, misconception-mapped |
| Flow Card Selection | ✅ Complete | Weighted buckets, conversation injection, dev overrides |
| Conversation Engine | ✅ Complete | Multi-turn, corrections, evaluation, engagement |
| Interest Tracking | ✅ Complete | 5-signal weighted scoring, topic theming |
| Session Management | ✅ Complete | Start/resume, XP, streaks, response logging |
| Persona Selection | ⚠️ Partial | Algorithm works but no YAML files → only Marta |
| Word System | ⚠️ Partial | Cards work but word pool is tiny (~16 seeds) |
| Dev Panel | ⚠️ Partial | Controls exist, state display broken (fix prompt ready) |
| Story Comprehension | ❌ Placeholder | Type defined but no generation/rendering |
| Persona Memories | ❌ Not built | Tables designed, no code |
| User Profile | ❌ Not built | Designed, no code |
| Placement/Onboarding | ❌ Not built | Prompt exists |
| Advanced Card Types | ❌ Not built | Fill-in-blank, sentence builder, listening |

---

## Where to Improve the Engine

### High Impact, Ready to Build

**1. Create persona YAML files** (effort: small)
- Just write 3-4 YAML files for Marta, Diego, Abuela Rosa, Luis
- The loader and selection code already exists
- Instant variety in conversations

**2. Grow the word pool** (effort: medium)
- Improve conversation word harvesting
- Use word taps to prioritize what to teach
- Words produced in conversation → skip intro, enter as "practicing"
- Biggest bottleneck right now: only 16 words tracked

**3. Persona memories** (effort: medium)
- Store 15-20 memories per persona from conversation evaluation
- Inject into system prompt: "You remember that the user likes cats"
- Makes repeat conversations feel connected, not amnesiac

**4. Stronger conversation evidence in BKT** (effort: tiny)
- Currently conversation evidence weighted same as MCQ
- Production (speaking) should count more than recognition (MCQ)
- ~10 lines to change

### Medium Impact

**5. Story comprehension cards** — nice variety from MCQ-heavy flow
**6. Interest-driven word selection** — teach words from topics user cares about
**7. Multi-dimensional skill tracking** — separate vocab/grammar/fluency/comprehension
**8. Fill-in-the-blank cards** — different testing modality

### Lower Priority

**9. Placement conversation** — better cold start than starting at zero
**10. CEFR tracking** — already extracted in evaluation, just need to store + use

---

## Key Config Numbers

```
Bucket weights:        spot=0.30  practice=0.50  new=0.20
Conversation every:    5 cards
Max conversation turns: 4
Mastery threshold:     0.90 (with min 5 attempts)
BKT learn rate:        0.10
BKT guess rate:        0.25
BKT slip rate:         0.10
Persona selection:     engagement×0.6 + novelty×0.3 + random×0.1
Novelty max bonus:     5 days since last conversation
```

All bucket weights and conversation frequency are tunable via dev overrides.
