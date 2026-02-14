# Spanish Vibes: Implementation Plan & Claude Code Prompts

*Generated: 2026-02-13*

---

## Strategy: Keep the Prototype, Build Toward Product

**Recommendation:** Don't start from scratch. Your prototype has real infrastructure (BKT, SRS, concept DAG, AI generation, 90+ lessons). Use it as a **design sandbox** to validate ideas, then migrate the proven logic into a production stack.

**Why:** The biggest unknowns aren't technical — they're "does the feed algorithm feel good?" and "does interest-based content increase engagement?" You can answer those faster by extending what you have than by rebuilding from zero.

**The plan is in two tracks:**
- **Track A (Weeks 1-4):** Extend the prototype to validate core ideas
- **Track B (Weeks 5+):** Build the production mobile app, porting proven logic

---

## Important Context: Competitive Landscape

**Parrot** (Y Combinator-backed) already exists as "TikTok for language learning" using comprehensible input theory. Your differentiation is **interest-driven immersion** — learning Spanish through content about things you actually care about. This is a genuinely open gap in the market. Parrot does passive comprehensible input; you'd do active, personalized, interest-driven practice.

**Market:** $101.5B language learning market (2026), 22.9% CAGR. EdTech freemium-to-paid conversion runs 5-8% (much higher than typical apps). Subscription pricing: $7-13/month.

**Retention is the killer:** Day 30 retention for education apps is 2-3%. If you can hit 20% Day 30 retention through the interest-based feed, you win.

---

## Track A: Prototype Validation (Weeks 1-4)

### Phase 1: Interest Tracking & Signal Collection (Week 1)

**Goal:** Add an interest model layer alongside the existing BKT system. Start collecting engagement signals that disambiguate interest from struggle.

#### Prompt 1: Interest Data Model & Signal Tracking

```
I'm building a TikTok-style Spanish learning app. I have an existing FastAPI + SQLite
app at /path/to/spanish-vibes with Bayesian Knowledge Tracing (BKT) in bkt.py,
flow mode in flow.py/flow_routes.py/flow_db.py, and AI MCQ generation in flow_ai.py.

I need to add an interest tracking system alongside the existing linguistic model.

Please do the following:

1. Add new tables to db.py:
   - `interest_topics`: id, name, parent_id (for hierarchy like "sports" > "football"),
     slug, created_at
   - `user_interest_scores`: topic_id, score (float 0-1), last_updated,
     interaction_count, decay_half_life_days (default 45)
   - `card_signals`: card_id, session_id, dwell_time_ms, was_correct (bool),
     response_time_ms, was_skipped (bool), topic_id, concept_id,
     card_type (mcq/fillblank/conversation/teach), created_at

2. Create a new file interest.py with:
   - InterestTracker class that:
     - Updates topic scores based on signals using this formula:
       engagement_signal = (0.40 * correctness) + (0.30 * normalized_dwell)
         + (0.15 * return_frequency) + (0.10 * progression) + (0.05 * continuation)
     - Disambiguates interest from struggle: long dwell + correct = interested,
       long dwell + wrong = struggling (don't boost interest score)
     - Applies exponential time decay: score * 0.5^(days_elapsed / half_life)
     - Has a get_top_interests(n=5) method returning ranked topics
     - Has an update_from_card_signal(signal: CardSignal) method

3. Seed the interest_topics table with ~20 common topics:
   sports, technology, music, food/cooking, travel, movies/tv, science,
   politics/news, fashion, gaming, fitness, business, art, history,
   nature/animals, relationships, literature, health, cars, photography

4. Write tests in tests/test_interest.py covering:
   - Score increases when correct + high dwell
   - Score does NOT increase when incorrect + high dwell (struggling)
   - Time decay reduces old scores
   - Top interests ranking works correctly

Keep the existing code intact. This is additive.
```

#### Prompt 2: Wire Signals Into Flow Mode

```
In the spanish-vibes app, I've added interest tracking (interest.py) and signal
collection tables (card_signals in db.py).

Now I need to wire signal collection into the existing Flow Mode routes.

In flow_routes.py:
1. After each card answer (POST /flow/answer), create a CardSignal record with:
   - dwell_time_ms: calculated from when the card was served to when answer came in
   - was_correct, response_time_ms from the existing answer evaluation
   - topic_id: for now, set to None (we'll add topic tagging to cards later)
   - card_type from the card metadata
2. Call interest_tracker.update_from_card_signal() with the signal
3. Store the signal in the card_signals table

In flow.py (card selection):
1. After selecting the linguistic concept (existing BKT logic), check the user's
   top interests via interest_tracker.get_top_interests(5)
2. Pass the top interest topics to the card generation step (flow_ai.py)
   so it can theme content around interests
3. Keep existing concept selection unchanged — interests only affect content
   theming, not which grammar concept is tested

Don't break any existing tests. Add new tests for the signal collection flow.
```

---

### Phase 2: Interest-Aware Content Generation (Week 2)

**Goal:** Extend the AI content pipeline to generate cards themed around user interests.

#### Prompt 3: Topic-Aware Card Generation

```
In the spanish-vibes app, flow_ai.py generates MCQ cards using GPT-4o-mini.
I need to extend it to generate cards themed around user interests.

Current flow_ai.py generates MCQs for a grammar concept. I need to:

1. Add a `topic` parameter to the generation function. When provided, the AI
   prompt should ask for content themed around that topic.

   Example: If concept is "preterite tense" and topic is "football",
   generate an MCQ like:
   "El equipo _____ el partido ayer." (ganó / ganará / gana / ganar)
   Instead of generic: "Ella _____ al mercado ayer."

2. Update the system prompt to include topic context:
   "Generate {count} multiple-choice questions testing {concept} at {difficulty}
   level. Theme the content around {topic}. Use vocabulary and scenarios related
   to {topic}. Ensure the grammar being tested is {concept}, not vocabulary."

3. Add a fallback: if topic-themed generation fails or returns poor quality,
   fall back to generic (no topic) generation.

4. Update the MCQ cache key to include topic: {concept}:{topic}:{difficulty}

5. For the "teach" card type, generate topic-themed explanations:
   "Here's how the preterite tense works — let's see it in action with football:
    'Madrid ganó la Liga.' (Madrid won the league.)"

6. Add a new card type: "conversation_opener" — generates a 1-2 sentence
   conversation starter in Spanish on the user's interest topic at their level.
   Example: "¿Viste el partido de ayer? ¿Qué piensas del resultado?"

Write tests that verify:
- Topic-themed MCQs still test the correct grammar concept
- Fallback works when topic generation fails
- Cache keys include topic
- Conversation openers are generated at appropriate difficulty
```

#### Prompt 4: Content Sourcing via Web Search (Optional Enhancement)

```
In the spanish-vibes app, I want to add a content sourcing module that pulls
trending topics to keep the interest-based content fresh and relevant.

Create a new file content_source.py that:

1. Has a TrendingTopics class with methods:
   - fetch_trending(language="es", count=10) -> list[TopicSummary]
     Uses web search or RSS to find current trending topics in Spanish
   - extract_keywords(topic: TopicSummary) -> list[str]
     Pulls out key Spanish vocabulary from the topic
   - map_to_interests(topic: TopicSummary, interests: list[InterestTopic])
     -> InterestTopic | None
     Maps a trending topic to an existing interest category

2. TopicSummary dataclass with: title, summary (2-3 sentences), keywords,
   source_url, published_date, language

3. A daily refresh function that:
   - Fetches top 10 trending topics
   - Maps them to interest categories
   - Pre-generates 3-5 cards per topic for the most popular interest categories
   - Caches results with 24-hour TTL

4. For MVP, use Google News RSS (free, no API key needed):
   - URL: https://news.google.com/rss?hl=es&gl=ES&ceid=ES:es
   - Parse with feedparser library

Keep it simple — this is a prototype. No need for spaCy or heavy NLP.
The LLM can extract keywords and map topics when generating cards.
```

---

### Phase 3: Conversation Cards (Week 3)

**Goal:** Add conversation as a card type in the feed.

#### Prompt 5: Conversation Card Engine

```
In the spanish-vibes app, I need to add a conversation card type to the
Flow Mode feed. This is a card where the AI starts a mini-conversation
in Spanish and the user responds.

Create a new file conversation.py with:

1. ConversationCard class:
   - topic: str (from user interests)
   - concept: str (grammar concept being practiced)
   - difficulty: int (1-3)
   - opener: str (AI's opening message in Spanish)
   - max_turns: int (default 4 — 2 AI + 2 user messages)
   - messages: list[ConversationMessage]

2. ConversationMessage dataclass:
   - role: "ai" | "user"
   - content: str
   - corrections: list[Correction] | None
   - timestamp: datetime

3. Correction dataclass:
   - original: str (what user said)
   - corrected: str (what it should be)
   - explanation: str (brief grammar note)
   - concept_id: str (links to concept DAG)

4. ConversationEngine class with methods:
   - generate_opener(topic, concept, difficulty) -> str
     Creates a natural conversation starter themed around the topic
     that will elicit use of the target grammar concept
   - evaluate_response(user_text, concept, difficulty) -> EvaluationResult
     Uses LLM to: check grammar, identify errors, generate corrections
     using the RECAST technique (reformulate naturally, don't lecture)
   - generate_reply(conversation_so_far, topic, concept) -> str
     Continues the conversation naturally while recasting any errors
     from the user's last message
   - should_end(conversation) -> bool
     Returns True if max_turns reached or conversation has natural endpoint
   - generate_summary(conversation) -> ConversationSummary
     Post-conversation: lists corrections, concepts practiced, score

5. The LLM prompt for conversation should use the TRACI framework:
   - Task: conversational practice
   - Role: friendly peer (not teacher)
   - Audience: A2 level (or user's current CEFR estimate)
   - Create: natural dialogue, 1-2 sentences per turn
   - Intent: build confidence + practice {concept}

6. Error correction strategy:
   - During conversation: use RECASTS only (reformulate errors naturally
     in the AI's response without explicit correction)
   - After conversation: show explicit corrections with explanations

Add to flow_routes.py:
   - POST /flow/conversation/start — starts a conversation card
   - POST /flow/conversation/respond — user sends a message
   - GET /flow/conversation/summary — post-conversation review

Add a conversation card template (templates/partials/flow_conversation.html)
that shows chat bubbles with:
   - AI messages on the left (gray bubbles)
   - User messages on the right (brand color bubbles)
   - Text input + microphone icon at bottom
   - "Done" button that ends conversation and shows summary
   - Corrections highlighted: green = correct, orange = corrected

Write tests covering:
   - Opener generation includes target concept
   - Error detection catches common A2 mistakes
   - Recast reformulates without explicit "you made an error" language
   - Conversation ends after max_turns
   - Summary includes all corrections
```

#### Prompt 6: Integrate Conversations Into the Feed

```
In the spanish-vibes app, the Flow Mode feed currently only serves MCQ and
teach cards. I need to mix in conversation cards.

In flow.py, update the card selection algorithm:

1. Add card type selection AFTER concept selection:
   - 60% MCQ cards (existing)
   - 15% fill-in-the-blank (existing)
   - 10% conversation cards (new)
   - 10% teach cards (existing)
   - 5% listening cards (placeholder for later)

2. Don't serve two conversation cards in a row — they're high-effort.
   Track last_card_type in session state and skip conversation if the
   previous card was also a conversation.

3. Don't serve conversation cards in the first 3 cards of a session
   (let the user warm up with MCQs first).

4. For conversation cards, pre-generate the opener in the background
   when the user is on card N-1 (preloading).

5. Update flow_routes.py to handle the conversation card flow:
   - When a conversation card is selected, return the opener via HTMX
   - User responses go to /flow/conversation/respond
   - When conversation ends, show summary, then "Next" button
     continues the regular feed

6. Collect signals from conversations:
   - Number of turns completed
   - Number of errors
   - Time spent (conversation dwell time is a strong interest signal)
   - Topic of conversation (for interest tracking)

Keep existing card types working unchanged. This is purely additive.
```

---

### Phase 4: Cold Start & Onboarding (Week 4)

#### Prompt 7: Adaptive Placement Test & Interest Selection

```
In the spanish-vibes app, I need to add a cold-start onboarding flow
for new users.

Create a new file onboarding.py with:

1. PlacementTest class:
   - Generates 5-10 adaptive questions using existing concept DAG
   - Starts at A2 mid-level, adjusts up/down based on answers
   - Each question tests a different concept area (verbs, vocab, grammar)
   - Uses item response theory (simple version): if correct, next question
     is harder; if wrong, easier
   - Returns estimated CEFR level (A1, A2, B1) and list of
     mastered/unmastered concepts

2. InterestSelector class:
   - Presents 15-20 topic cards with icons
   - User taps to select 3-5 interests
   - Stores selections in user_interest_scores with initial score of 0.5
   - Optional: "What's your goal?" selector (casual, travel, work, exam)

3. CurriculumGenerator class:
   - Takes placement result + interests + goal
   - Generates a 7-day initial curriculum using LLM
   - Curriculum = ordered list of (concept, topic, card_type) triples
   - First day: heavier on teach cards; subsequent days: more MCQ + conversation
   - Stores curriculum in a new `user_curriculum` table

4. Onboarding flow:
   - GET /onboarding → placement test page
   - POST /onboarding/answer → adaptive next question
   - GET /onboarding/interests → interest selection page
   - POST /onboarding/complete → generates curriculum, redirects to /flow

5. Templates:
   - templates/onboarding_test.html — clean, full-screen quiz UI
   - templates/onboarding_interests.html — grid of topic cards to tap

6. After onboarding, the feed algorithm uses the curriculum for days 1-3
   (70% curriculum, 30% exploration), then transitions to full adaptive
   mode by day 7.

Write tests for:
   - Placement test adapts difficulty based on answers
   - Interest selections are stored correctly
   - Curriculum covers a mix of concepts and topics
   - Onboarding flow completes end-to-end
```

---

## Track B: Production Build (Weeks 5+)

### Recommended Production Stack

| Layer | Choice | Why |
|-------|--------|-----|
| Mobile | React Native + Expo | TikTok swipe UX, JS ecosystem, speech APIs |
| Backend API | FastAPI (keep it) | Async streaming, LLM integration, momentum |
| Database | Postgres (Supabase) | pgvector for interests, real-time, managed |
| Job Queue | Inngest or Celery | Background card pregeneration |
| Real-Time | SSE (StreamingResponse) | Simple, unidirectional, FastAPI native |
| Speech | Whisper API + expo-speech | $0.02/min transcription, native TTS |
| Hosting | Railway (API), Supabase (DB) | Generous free tiers, fast deploys |

#### Prompt 8: Migrate to Postgres

```
I'm migrating the spanish-vibes FastAPI app from SQLite to PostgreSQL
(Supabase). The current schema is in db.py with tables for cards, decks,
lessons, flow_sessions, concept_knowledge, mcq_cards, plus the new tables
I've added (interest_topics, user_interest_scores, card_signals).

Please:

1. Create a migration script (migrations/001_initial.sql) that converts
   the SQLite schema to PostgreSQL:
   - Replace AUTOINCREMENT with SERIAL
   - Replace TEXT for JSON columns with JSONB
   - Add proper indexes (especially on card_signals for analytics queries)
   - Add a pgvector column to user_interest_scores for future embedding-based
     interest matching

2. Update db.py to use asyncpg instead of sqlite3:
   - Replace connection handling with async connection pool
   - Update all queries for Postgres syntax differences
   - Keep the same public API so nothing else breaks
   - Use environment variable DATABASE_URL for connection string

3. Create a data migration script that exports existing SQLite data
   and imports it into Postgres.

4. Update all tests to work with both SQLite (for local dev) and
   Postgres (for CI/production). Use a DATABASE_URL env var to switch.

5. Update pyproject.toml with new dependencies: asyncpg, python-dotenv
```

#### Prompt 9: React Native Mobile App Shell

```
I'm building a React Native + Expo mobile app for a TikTok-style Spanish
learning app. The backend is FastAPI at [API_URL].

Create the initial mobile app with:

1. Project setup with Expo (expo init spanish-vibes-mobile)
   - TypeScript template
   - Dependencies: react-query, react-native-reanimated, react-native-gesture-handler,
     expo-speech, expo-av

2. Navigation structure:
   - Onboarding screens (placement test, interest selection)
   - Main feed (full-screen swipeable cards)
   - Profile/stats screen
   - No tab bar — the feed IS the app (like TikTok)

3. Card feed component:
   - Full-screen vertical swipe (swipe up = next card)
   - Preloads next 2 cards via react-query prefetch
   - Card types render different components:
     - MCQCard: question + 4 option buttons
     - FillBlankCard: sentence with text input
     - ConversationCard: chat bubbles + text input + mic button
     - TeachCard: explanation with "Got it" button
   - Swipe animation with react-native-reanimated

4. API service layer:
   - GET /flow/next-card — fetches next card
   - POST /flow/answer — submits answer
   - POST /flow/conversation/respond — conversation message
   - GET /flow/stats — session stats
   - SSE connection for streaming AI responses

5. Local card cache using MMKV:
   - Cache fetched cards for offline use
   - Store up to 10 cards ahead

6. Basic styling:
   - Dark theme (like TikTok)
   - Large, readable text for Spanish content
   - Bottom-aligned interaction area (thumb-friendly)
   - Smooth card transitions

This is the shell — get the swipe feed working with mock data first,
then wire up the API.
```

#### Prompt 10: Preloading System

```
In the spanish-vibes mobile app (React Native + Expo), I need to implement
a card preloading system so the user never waits for content.

Implement:

1. CardPreloader service:
   - When user is on card N, preload cards N+1 and N+2
   - For MCQ/fill-blank/teach cards: full preload (all data ready)
   - For conversation cards: preload only the opener (AI's first message)
   - Stagger requests: N+1 immediately, N+2 after 500ms delay

2. Backend changes (FastAPI):
   - GET /flow/preload?count=3 — returns next 3 cards in the queue
   - For conversation cards, only returns the opener, not full conversation
   - Each card includes an estimated_generation_time field so the client
     knows if it should show a loading skeleton

3. Cache management:
   - Store preloaded cards in react-query cache with 5-minute stale time
   - If user skips a card (swipe without answering), mark it as skipped
     in the signal tracker but don't waste the generation
   - Track preload hit rate: % of cards that were ready when user swiped

4. Adaptive buffer size:
   - If user skips frequently (>40% skip rate): reduce to 1 card ahead
   - If user engages deeply (<20% skip rate): increase to 3 cards ahead
   - Track per-session and adjust dynamically

5. SSE stream for conversation cards:
   - When user enters a conversation card, open SSE connection
   - Stream AI responses token-by-token for natural feel
   - Show typing indicator while streaming

6. Fallback: if preloaded card isn't ready, show a brief loading skeleton
   (not a spinner — skeleton feels faster)
```

---

## Conversation Card UX Design Spec

(For reference when building the conversation card component)

```
┌─────────────────────────────────────┐
│ [Topic badge: "Deportes"]  [A2]     │  ← Header
│                                     │
│  ┌─────────────────────────┐        │
│  │ ¿Viste el partido de    │        │  ← AI bubble (left, gray)
│  │ ayer? ¡Fue increíble!   │        │
│  └─────────────────────────┘        │
│                                     │
│        ┌─────────────────────┐      │
│        │ Sí, yo lo vi. El   │      │  ← User bubble (right, blue)
│        │ equipo jugó bien.  │      │
│        └─────────────────────┘      │
│                                     │
│  ┌─────────────────────────┐        │
│  │ ¡Claro! El equipo jugó  │        │  ← AI recast (corrects subtly)
│  │ muy bien. ¿Cuál fue tu  │        │
│  │ momento favorito?       │        │
│  └─────────────────────────┘        │
│                                     │
│                                     │
│                                     │
│ ┌─────────────────────────────────┐ │
│ │ Escribe en español...     🎤   │ │  ← Input (text + mic toggle)
│ └─────────────────────────────────┘ │
│           [ Done ✓ ]                │  ← End conversation
└─────────────────────────────────────┘

After tapping "Done":

┌─────────────────────────────────────┐
│ Conversation Summary                │
│                                     │
│ ✅ 3 correct responses              │
│ 📝 1 correction:                    │
│    "jugó bien" → "jugó muy bien"    │
│    (intensifiers with adverbs)      │
│                                     │
│ Concepts practiced:                 │
│  • Preterite tense ████████░░ 80%   │
│  • Sports vocabulary ██████████ 95% │
│                                     │
│         [ Next Card → ]             │
└─────────────────────────────────────┘
```

---

## Signal Disambiguation Quick Reference

When collecting card signals, use this logic:

```python
def classify_engagement(dwell_ms, was_correct, response_time_ms, was_skipped):
    if was_skipped:
        return "disengaged"  # Don't boost any scores

    # Normalize dwell time (expected range: 5s-60s for most cards)
    dwell_s = dwell_ms / 1000

    if was_correct and dwell_s > 10:
        return "interested"     # Took time AND got it right = genuine engagement
    elif was_correct and dwell_s <= 10:
        return "easy"           # Quick + correct = too easy, don't over-weight interest
    elif not was_correct and dwell_s > 15:
        return "struggling"     # Slow + wrong = struggling, don't boost interest
    elif not was_correct and dwell_s <= 5:
        return "guessing"       # Too fast + wrong = random guess
    else:
        return "learning"       # Normal learning signal
```

---

## Key Metrics to Track From Day 1

| Metric | Target | Why |
|--------|--------|-----|
| Day 1 retention | >25% | First session hook working |
| Day 7 retention | >15% | Feed algorithm engaging |
| Day 30 retention | >8% | Interest personalization working (industry avg: 2-3%) |
| Time to First Personalization | <5 min | User feels "this gets me" |
| Cards per session | 15-25 | Sweet spot for learning + engagement |
| Conversation completion rate | >60% | Conversations aren't too hard/boring |
| Interest prediction accuracy | >70% | User engages with predicted topics |
| Preload hit rate | >85% | No waiting between cards |
| Skip rate | <30% | Content is relevant |
| Premium conversion | 5-8% | Business viability |

---

## Prompt Sequencing for Claude Code

**Run these in order:**

1. **Prompt 1** → Interest data model & signals (foundation)
2. **Prompt 2** → Wire signals into Flow Mode (connects to existing code)
3. **Prompt 3** → Topic-aware content generation (makes interests useful)
4. **Prompt 4** → Content sourcing (optional, enhances freshness)
5. **Prompt 5** → Conversation card engine (new card type)
6. **Prompt 6** → Integrate conversations into feed (mix card types)
7. **Prompt 7** → Cold start onboarding (first-run experience)

*After validating the above in the prototype:*

8. **Prompt 8** → Postgres migration (production database)
9. **Prompt 9** → React Native app shell (mobile frontend)
10. **Prompt 10** → Preloading system (performance polish)

**Each prompt is designed to be self-contained** — you can feed it directly to Claude Code and it should work without additional context (assuming previous prompts have been completed).
