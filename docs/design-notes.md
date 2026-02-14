# Spanish Vibes → TikTok-for-Learning: Design Notes

*Started: 2026-02-13*
*Status: Early exploration / brainstorming*

---

## The Vision

A low-user-agency language learning app — like TikTok meets Duolingo. Instead of the user navigating lessons and choosing what to study, the app **serves a continuous feed of learning content** adapted to the user in real time. Think of it as "Duolingo but free-form, the TikTok version" — interactive, with buttons, speech, conversations, and discussions.

### Core Principles

1. **Push, not pull.** The user doesn't choose content — the app decides what to serve next. Low agency, high engagement.
2. **Personalized interest layer.** Content is themed around what the user actually cares about (news, hobbies, culture), so learning feels relevant rather than generic.
3. **Multiple interaction modes.** MCQs, fill-in-the-blank, free-form conversation, listening, pronunciation — mixed into a single feed for variety.
4. **Two-dimensional adaptation.** The algorithm tracks *linguistic ability* (what grammar/vocab you know) AND *personal interests* (what topics engage you). Both shape the feed.

---

## What Exists Today

The current `spanish-vibes` prototype already has significant infrastructure:

- **Bayesian Knowledge Tracing (BKT)** for concept mastery (90% threshold, min 5 attempts)
- **Spaced Repetition (SM-2 variant)** with ease/interval tracking
- **Flow Mode v2** — an adaptive feed that selects cards based on mastery buckets (30% mastered, 50% learning, 20% new)
- **AI MCQ generation** via GPT-4o-mini with misconception mapping per distractor
- **Concept prerequisite DAG** — topological ordering ensures learners don't get advanced content before foundations
- **90+ markdown lessons** organized in 30 chapters, each with vocab, fill-in-blank, verb conjugations
- **HTMX-based UI** — already does partial page swaps for card-by-card interaction

**Flow Mode is already a proto-feed.** The main evolution is adding the interest layer and diversifying card types.

---

## Big Design Questions

### 1. Interest Tracking System
**Status:** Needs research

How do we build a user interest profile from implicit signals?

**Signals to capture:**
- Time spent on a card (longer = more engaged?)
- Conversation continuation (chose to keep talking about a topic)
- Which distractor misconceptions align with topic areas
- Response quality on interest-aligned vs generic content
- Explicit thumbs up / "more like this" (optional, breaks low-agency model?)

**Open questions:**
- What's the right data model for interests? Tags? Embeddings? Topic hierarchy?
- How do you weight implicit signals vs explicit ones?
- How granular should interest categories be? ("sports" vs "Formula 1" vs "Max Verstappen")
- How quickly should the interest profile shift? (TikTok adapts in minutes)
- Should interests decay over time? (News stories go stale)

**Research needed:** How do recommendation systems in education handle interest modeling? What does TikTok's approach look like at a high level? Are there open-source implementations to learn from?

---

### 2. Content Generation Pipeline
**Status:** Needs research

If content is personalized to interests, it can't all be hand-written. The app needs to generate learning content on the fly.

**Current pipeline:** Markdown lessons → parsed cards → DB → served via Flow Mode
**Future pipeline:** Interest profile + linguistic level + news/topic APIs → AI generates cards → quality filter → served in feed

**Key components needed:**
- **Content sourcing:** News APIs (NewsAPI, RSS feeds, etc.) for real-world topics
- **AI generation:** Extend `flow_ai.py` from "generate MCQs for a grammar concept" to "generate MCQs for a grammar concept themed around [topic]"
- **Quality validation:** Linguistic accuracy, factual accuracy, difficulty calibration
- **Caching strategy:** Pre-generate content for popular topic × concept combinations? Or generate on-demand?

**Open questions:**
- How do you ensure AI-generated Spanish is actually correct and natural?
- What's the latency budget? Can we generate in real-time or must we pre-generate?
- How do we handle content that's factually time-sensitive (news that changes)?
- Cost implications of heavy AI generation — can we cache/reuse effectively?

**Research needed:** What news/content APIs are available and affordable? What's the state of the art for AI-generated language learning content? Latency and cost benchmarks for GPT-4o-mini at scale.

---

### 3. Conversational Interaction Model
**Status:** Needs research

One of the most differentiating features — actual free-form conversations in Spanish, themed around user interests.

**Concept:** The app opens a conversation about something you care about. You respond in Spanish. The AI evaluates your response, gently corrects errors, and continues the conversation. This is a high-engagement card type mixed into the feed.

**Design considerations:**
- How long should conversations be? (2-3 turns? Open-ended?)
- How does error correction work without killing flow? (Inline corrections? Post-conversation summary?)
- How do you evaluate spoken input? (Web Speech API → text → AI evaluation?)
- How does conversation difficulty adapt? (Simpler prompts for beginners, more nuanced for advanced)
- How do conversations feed back into the interest and linguistic models?

**Open questions:**
- What does the UI look like for a conversation card vs an MCQ card?
- Should conversations be async (type at your own pace) or have a time pressure?
- How do you prevent the AI from being too lenient or too strict in correction?
- Can conversation transcripts become source material for future cards?

**Research needed:** What are existing AI conversation tutors doing? (ChatGPT language mode, Duolingo Max, etc.) What works and what doesn't? Web Speech API capabilities and limitations.

---

### 4. Feed Algorithm Design
**Status:** Needs design

The core algorithm that decides "what card to show next."

**Current Flow Mode logic:**
```
Buckets: mastered (30%) → learning (50%) → new (20%)
Within bucket: weighted random by BKT probability
Prerequisite check: don't serve concepts with unmet prerequisites
```

**Proposed evolution:**
```
Input signals:
  - Linguistic state (BKT mastery per concept)
  - Interest profile (topic affinities)
  - Session context (variety, fatigue, streak)
  - Content availability (what's cached/generated)

Card selection:
  1. Choose concept to reinforce (BKT-driven)
  2. Choose topic overlay (interest-driven)
  3. Choose card type (variety-driven — MCQ, conversation, fill-blank, teach, listen)
  4. Generate or fetch card matching (concept × topic × type)
  5. Serve card, collect signal, update both models
```

**Open questions:**
- How do you balance exploration (trying new topics/concepts) vs exploitation (reinforcing known interests/weak concepts)?
- What's the right session pacing? (Don't serve 5 MCQs in a row, mix in conversations and teach cards)
- How do you handle the "nothing available" case? (No cached content for this concept × topic combo)
- Should there be any user override? ("I'm bored of this topic" button?)

---

### 5. Cold Start Problem
**Status:** Needs research

How does the app work before it knows anything about you?

**Options:**
- **Light onboarding:** Pick 3-5 interest areas, do a quick placement test for level
- **TikTok approach:** Serve a diverse mix, observe engagement, converge quickly
- **Hybrid:** Brief interest selection + diverse content mix that narrows over first 20-30 cards

**Open questions:**
- How many interactions before the interest profile is useful?
- How many interactions before linguistic level is calibrated?
- What does the "generic" content feed look like before personalization kicks in?
- Can we use the existing lesson content as cold-start material?

---

### 6. Speech & Audio Integration
**Status:** Needs research

The "interactive with speech" aspect.

**Potential features:**
- **Text-to-speech:** App reads Spanish content aloud (pronunciation model)
- **Speech-to-text:** User speaks Spanish, app evaluates pronunciation
- **Listening comprehension:** Audio-only cards where you hear Spanish and respond
- **Conversation mode:** Spoken back-and-forth with the AI

**Open questions:**
- Web Speech API vs cloud speech services (Google, Azure, Whisper)?
- How good is browser-based Spanish speech recognition?
- How do you score pronunciation meaningfully?
- Does audio add enough value to justify the complexity early on?

---

## Architecture Evolution Sketch

```
Current:
  [Markdown Lessons] → [Parser] → [SQLite DB] → [Flow Mode] → [HTMX UI]
                                                      ↑
                                                  [BKT + SRS]

Future:
  [News APIs / RSS]  →  [Content Engine]  →  [Card Cache]  →  [Feed Algorithm]  →  [UI]
  [User Interests]   →       ↑                                      ↑
  [Concept Graph]    →  [AI Generation]                    [BKT + Interest Model]
  [Existing Lessons] →  [Quality Filter]                         ↑
                                                          [User Signals]
```

---

## Next Steps

1. **Research phase** — Investigate interest tracking, content generation, conversational AI, cold start strategies
2. **Design the interest data model** — How interests are stored, updated, queried
3. **Prototype the extended content pipeline** — Add topic-awareness to `flow_ai.py`
4. **Design the unified card type system** — All card types as variants in a single feed
5. **Iterate on the feed algorithm** — Extend Flow Mode with interest-awareness
6. **Explore speech integration** — Feasibility and value assessment

---

## Research Log

### Interest Tracking & Recommendation Systems

**Key finding:** Start simple — completion rate + dwell time gives ~70% of the value. The most practical approach is a hybrid: content-based filtering (tag your content by topic/difficulty/type) combined with lightweight collaborative filtering once you have enough users.

**Interest modeling options explored:**
- Tag-based scoring (simplest, good for MVP — sorted set in Redis with topic scores)
- Embeddings / topic models (LDA2Vec, ETM — better for discovering latent interests)
- Knowledge graphs (you already have the concept DAG — extend it with topic dimensions)
- Session-based RNNs (GRU4Rec — captures sequential patterns within learning sessions)

**TikTok's transferable patterns:** They use a multi-stage pipeline (candidate generation → ranking → filtering) with real-time streaming updates. Key signals: completion rate, rewatch rate, dwell time. They optimize for multiple engagement types simultaneously via multi-task learning. The critical difference for education: optimize for learning outcomes + sustained engagement, not just session time.

**Explore-exploit:** Thompson Sampling or UCB (Upper Confidence Bound) prevent recommendation echo chambers. Practical formula: `Score = 0.7 * predicted_engagement + 0.2 * diversity_bonus + 0.1 * exploration_bonus`. Every 5th recommendation, force exploration of less-familiar territory.

**Open-source tools:** Gorse (Go, production-ready), LensKit (Python, research), TensorFlow Recommenders (deep learning), GRU4Rec (session-based).

**MVP data model:** Redis sorted sets for topic scores + SQLite for persistent history. Update tag scores in real-time, batch-recompute collaborative signals hourly. Track interests at multiple granularities (coarse: "sports" → fine: "Formula 1").

---

### Content Generation Pipeline

**Key finding:** A solo-dev MVP is feasible at ~$30-50/month for 1,000 active users.

**Content sourcing:**
- Google News RSS (free, zero config, Spanish editions available) — best for MVP
- MediaStack free tier as backup
- El País, BBC en Español, CNN en Español RSS feeds for Spanish-specific content
- Upgrade to NewsAPI.ai ($3-5/month) when you need volume

**AI generation costs:**
- GPT-4o-mini: $0.15/1M input, $0.60/1M output — ~$4.20/month for 30,000 exercises
- Claude Haiku: $0.80/1M input, $5/1M output — more expensive but comparable quality
- Both achieve sub-second latency (0.5s to first token)

**Recommended pipeline:**
1. Daily cron job fetches top 10 trending Spanish topics from RSS
2. spaCy (`es_core_news_sm`) extracts named entities and keywords
3. GPT-4o-mini generates 3-5 exercises per topic (MCQ, fill-blank, conversation prompt)
4. LanguageTool API (free, 10K requests/day) validates grammar
5. Cache in Redis with 48-hour TTL, keyed by `{topic}:{difficulty}:{type}`
6. On user request: check cache first (1-5ms), generate on miss (500-800ms)

**Quality validation:** Multi-stage — automated grammar check (LanguageTool), semantic validation via cheap LLM call, human review of first 50-100 generated exercises to build prompt refinement rules. Research shows ~18.5% of GPT-4-generated Spanish needs adjustment initially.

**Tech stack:** feedparser + newspaper3k for RSS, spaCy for NLP, Redis for caching (self-hosted or Upstash at $0.2/100K ops).

---

### Conversational AI for Language Learning

**Key finding:** The differentiator isn't model quality (everyone uses GPT-4/Whisper) — it's interaction design and error correction strategy.

**What existing products do:**
- Duolingo Video Call: Short sessions (2-6 min), focused scenarios, transcripts for review. Research shows significant speaking improvements. Key insight: *short, time-boxed conversations outperform long-form tutoring in adoption.*
- ChatGPT Voice: Unlimited practice, no specialized pedagogy. Users want it to be more of a tutor.
- Speak, SpeakPal, Pingo: Largely similar — differentiation is marketing, not substance.

**Error correction — the recast technique (research-backed):**
- Reformulate the learner's error naturally without interrupting: Student says "Yo goes al mercado" → AI responds "Ah, vas al mercado. ¡Qué bien!"
- Preserves conversational flow while exposing learner to correct form
- For the app: use recasts IN-CARD (natural), defer detailed explanations to a POST-CARD review modal

**Prompting strategy — TRACI framework:**
- Task (conversation/conjugation/comprehension) + Role (peer/tutor/friend) + Audience (A1/B1/etc.) + Create (dialogue/correction) + Intent (confidence/accuracy/culture)
- Keep AI responses to 1-2 sentences max in conversation mode
- Scaffold difficulty: provide partial sentence structures at lower levels

**Evaluating free-form responses:**
- Automated: LLM-based grammar analysis + LanguageTool + vocabulary level check
- Post-conversation: LLM rates response on accuracy/vocabulary/fluency (1-5 scale each)
- Track CEFR-level estimates over time to build learner profile

**Web Speech API for Spanish:**
- Chrome/Edge support SpeechRecognition with multiple Spanish variants (Spain, Mexico, Argentina)
- Requires internet (sends audio to Google servers)
- Good for prototype; production apps should add cloud TTS fallback (Google Cloud, ElevenLabs)
- Always provide text input as fallback

**Open-source references:** Discute (speaking practice with Groq), Companion (end-to-end pipeline with OpenAI + Whisper + TTS), Open TutorAI (extensible platform with RAG).

---

### Cold-Start Strategies

**Key finding:** Combine a light adaptive placement test with LLM-generated initial curriculum. Useful personalization achievable within 3-5 interactions; strong convergence by day 3-5.

**What works from other apps:**
- TikTok: Diverse popular content → rapid implicit signal collection → useful personalization in minutes
- Spotify: Explicit onboarding (pick artists/genres) + implicit engagement tracking
- Duolingo: Adaptive placement test that adjusts difficulty per answer → unlocks appropriate level

**Recommended hybrid approach:**
1. **Onboarding (3 min total):** Adaptive placement test (5-10 questions, ~2 min) + interest selection (pick 3-5 topics) + goal selection (casual/exam/travel/professional)
2. **First session:** LLM generates initial 7-day curriculum based on level + interests + goals
3. **Days 1-3 (exploration phase):** 70% exploit / 30% explore across content types and topics
4. **Days 3-7 (transition):** 80% exploit / 20% explore, narrowing based on engagement signals
5. **Week 2+ (exploitation):** 90% personalized / 10% exploratory; add collaborative filtering once you have 50+ users

**Convergence timeline:**
- 3-5 interactions: System shows meaningful personalization
- 10-15 interactions: Recommendations become genuinely useful
- 30+ interactions: Algorithm converges to stable profile
- Placement test alone gets you ~70% accuracy on difficulty matching

**Implicit signals to track from day 1:** accuracy per concept, time per card, retry behavior, skip patterns, time-to-answer (too fast = overqualified, slow = underprepared), mistake repetition patterns.

**MVP implementation (~500 lines of business logic):**
- Placement test logic: ~200 lines
- Lesson metadata schema: ~50 lines
- LLM curriculum generation prompt: ~30 lines
- Implicit signal tracker: ~100 lines
- Daily lesson adjustment: ~150 lines

**Key metric:** Time to First Personalization should be <5 minutes. If the user feels the app "gets them" by the end of the first session, retention dramatically improves.

---

### Signal Disambiguation (Interest vs Struggle)

**Key finding:** Dwell time alone is ambiguous. The combination of dwell time + correctness is the minimum viable signal pair. Long dwell + correct = interested. Long dwell + wrong = struggling.

**Multi-signal classification:**

| Signal Combo | Meaning | Action |
|---|---|---|
| Correct + long dwell | Genuinely interested | Boost interest score |
| Correct + short dwell | Too easy | Don't boost interest, note overqualification |
| Wrong + long dwell | Struggling | Don't boost interest, offer help |
| Wrong + short dwell | Guessing/disengaged | Don't boost interest, vary content |
| Skipped | Disengaged from topic | Slightly reduce interest score |

**Frustration detection thresholds (from research):**
- 3+ consecutive errors on same concept = unproductive frustration → intervene
- Keystroke stress factor >1.4x baseline = frustration signal
- Return visits to same topic within 14 days = strong positive interest signal

**Interest decay formula:**
```
current_score = original_score * 0.5^(days_elapsed / half_life)
half_life = 45 days (for topic interests)
recency_multiplier = 1.5 if last_interaction < 7 days ago
```

---

### Competitive Landscape

**Key finding:** Parrot (YC-backed) already does "TikTok for language learning" using comprehensible input. Your differentiation is **interest-driven immersion** — learning through content about things you care about.

**Market:** $101.5B (2026), 22.9% CAGR. EdTech freemium-to-paid: 5-8%. Pricing: $7-13/month.

**Retention cliff:** Day 30 retention for education apps = 2-3%. Content exhaustion and plateau perception are the top killers. Feed-based infinite content could structurally address this.

**Positioning:** Parrot = "learn through science (comprehensible input)." You = "learn through your passions (interest-driven immersion)." Both valid, different markets.

---

### Tech Stack (Production)

**Recommendation:** React Native + Expo (mobile) → FastAPI (keep, it works) → Postgres/Supabase (pgvector for interests) → Inngest (background jobs) → SSE (real-time streaming).

**Key insight:** Keep FastAPI — it's production-ready, you have momentum, and switching backends mid-project is a trap. The big move is adding a real mobile frontend (React Native) and a real database (Postgres).

---

### Preloading Architecture

**Key finding:** Buffer 2-3 cards ahead, not more. For conversation cards, preload only the opener (AI's first message); stream the rest on-demand.

**Waste optimization:** ~25-35% skip rate is typical for feed-based content. Adaptive buffer size based on user behavior (heavy skippers get 1 card ahead, engaged users get 3). This is a real cost lever at scale.

**Tiered preloading:** N+1 = full quality, N+2 = medium quality, N+3 = metadata only.

---

### Conversation Card UX

**Key finding:** 4-6 exchanges is the sweet spot (1-2 minutes). Use recasts during conversation, show explicit corrections after. Text is default input, voice is enhancement (not requirement).

**Visual design:** Chat bubbles in a contained card. AI left (gray), user right (brand color). Input at bottom with keyboard + mic toggle. "Done" button for graceful exit → summary card with corrections and concept mastery.

**Keyboard/mic toggle:** Long-press mic for voice, tap text field for keyboard. Both always available, no mode switching. Show real-time transcript during speech. Allow inline editing if transcription is wrong.

---

### Conversation Engine Deep Dive (Research Round 2)

**Critical finding: Merge evaluate + reply into ONE API call.** Two calls per turn (evaluate grammar → generate reply) is slow, expensive, and disconnected. The reply doesn't even use the evaluation result. Research shows prompt chaining outperforms monolithic prompts for complex tasks, BUT for this specific case — where the recast IS the reply — a single structured-output call that evaluates AND responds is the right pattern. The evaluation informs the recast which IS the conversational response.

**Use OpenAI Structured Outputs (strict mode) for 100% reliable JSON.** With `response_format` + `json_schema` + `strict: true`, gpt-4o-2024-08-06 achieves perfect schema adherence vs <40% for raw JSON prompting. This solves the "sometimes the model returns garbage JSON" problem entirely.

**Use gpt-4o-mini for everything.** The current code uses gpt-4o for evaluation (expensive!). Grammar checking is a simple pattern-matching task — mini handles it fine. Cost difference: $0.60/1M output vs $15/1M output. 25x savings.

**Latency budget:** 300ms = natural conversational pause. GPT-4o-mini hits 150-300ms for 50 tokens. Stream the conversational reply immediately, show grammar feedback asynchronously after.

**What Speak does right:** Role-play scenarios as core interaction. Real-time feedback on pronunciation. Post-session error summary (not mid-conversation interruption). Emphasis on psychological safety — zero penalty for mistakes.

**What Duolingo does right:** Humans write scenarios first, AI executes. Characters have personality (Lily: "sarcastic deadpan teen with soft heart"). System prompt includes character backstory + user-specific facts. Conversations remember previous sessions. 2-6 minute sessions max.

**Key Duolingo insight: humans design the scenarios, AI just runs them.** Pure AI-generated scenarios have lower pedagogical quality. For MVP, hand-design 20-30 scenario templates per grammar concept, let AI fill in the topic/interest personalization.

**Persona matters.** Research shows AI tutors with consistent personas yield medium-to-large learning gains. Warm peer > authoritative teacher for language learning. The persona should have a name, backstory, consistent voice. Not "helpful AI tutor" but a character you'd actually want to talk to.

**The recast technique works but has a limitation:** Learners often don't notice recasts without explicit instruction. Solution: use recasts IN-conversation (natural correction) + show explicit corrections AFTER (conscious learning). The recast is the AI's reply; the corrections are the summary card.

**Scaffolding by difficulty:**
- A1: Offer partial sentences, vocabulary hints, brief English hints in parentheses. "You could say: Ayer yo _____ (ir = to go)"
- A1-A2: Occasional vocabulary help only if user seems stuck. No English.
- A2: Full Spanish, no hints. Challenge with more complex structures.

**Grammar forcing — concept steering prompts:**
- Preterite: "¿Qué hiciste ayer?" / "¿Adónde fuiste el fin de semana?" (forces past tense)
- Ser/Estar: "¿Cómo es tu ciudad?" vs "¿Cómo estás hoy?" (forces distinction)
- Gustar: "¿Qué tipo de música te gusta?" (forces gustar construction)
- Subjunctive: "Tu amigo tiene un examen. ¿Qué le recomiendas?" (forces espero que + subjunctive)

**Error tolerance research:** Only correct TARGET grammar errors. If practicing preterite and they make a ser/estar mistake, let it go. Focused correction > comprehensive correction. Allow 2-3 sentences before intervening. Self-correction is more effective than external correction.

**Conversation card structure (for 1-2 min):**
1. Setup (15-20s): Scenario context + AI opener that forces target grammar
2. Exchange 1 (20-30s): User responds, AI recasts errors naturally + continues
3. Exchange 2-3 (30-40s): Follow-up that slightly increases demand
4. Reflection (10-15s): Summary card with corrections + sample responses

**Anxiety reduction:** Text-first (lower anxiety than voice). No time pressure. Private practice (no leaderboards for conversations). Encouraging feedback. Frame as practice, not assessment.

---

### Multi-Persona System (Future Feature)

**Idea:** Instead of one persona (Marta), have multiple characters matched to interests and concepts. Each persona has topic affinities, a regional dialect, and a personality.

**Why this works:**
- One character can't authentically cover every topic. A journalism student talking about car mechanics feels off. Match persona to topic → natural conversations.
- Regional dialect exposure for free: Marta (Madrid) uses vosotros, Diego (Buenos Aires) uses vos, Sofía (Mexico City) uses ustedes. Real Spanish isn't monolithic.
- Progression mechanic: unlock new personas as you level up. Each has slightly different speech patterns and complexity. A1 = Marta (patient, simple). A2 = Diego (faster, slang). B1 = Professor García (formal, subjunctive-heavy).
- Replay value: same topic, different persona = different conversation. "Football with Diego" ≠ "Football with Marta."

**Persona-interest matching algorithm:**
```
For each persona:
  affinity_score = sum(persona.topic_weights[t] * user.interest_scores[t] for t in topics)
  level_match = 1.0 if persona.difficulty == user.level else 0.5
  recency_penalty = 0.7 if persona was used in last 3 conversations else 1.0
  final_score = affinity_score * level_match * recency_penalty

Select persona with highest final_score (with some randomness)
```

**Example personas (future):**
- **Marta** (Madrid, 25, journalism student) — warm, curious, slightly sarcastic. Topics: music, movies, food, current events. Level: A1-A2. Dialect: Peninsular Spanish.
- **Diego** (Buenos Aires, 30, sports journalist) — enthusiastic, uses Argentine slang (che, boludo). Topics: sports, travel, nightlife. Level: A2-B1. Dialect: Rioplatense.
- **Sofía** (CDMX, 28, software engineer) — chill, techy, direct. Topics: technology, gaming, science, startups. Level: A2-B1. Dialect: Mexican Spanish.
- **Profesor García** (Bogotá, 55, retired teacher) — formal, patient, loves literature. Topics: history, literature, art, philosophy. Level: B1+. Dialect: Colombian Spanish.
- **Lucía** (Barcelona, 22, art student) — creative, emotional, speaks fast. Topics: art, fashion, social media, relationships. Level: A2. Dialect: Catalan-influenced Spanish.

**Implementation note:** Start with Marta only. Add Diego as the second persona when the conversation engine is stable. The system prompt structure already supports swapping personas — just change the MARTA_PERSONA constant to a lookup.

**Not implementing yet** — get Marta working perfectly first. But design the conversation engine so persona is a parameter, not hardcoded.
