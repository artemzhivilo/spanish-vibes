# Spanish Vibes — Backlog

## Bugs

- [ ] **Word taps recording full sentences** — When user selects a whole sentence to translate, the word_taps table records the entire sentence as a single "word" (e.g. "te gusta más este chico que está aquí o ese que está allá" with 6 taps). Fix: only count single-word selections as word tap signals. Sentence translations can still be stored separately but shouldn't feed into word-level prioritization.

## Recently Done

- [x] Upgrade conversation corrections to `gpt-4o` (from `gpt-4o-mini`)
- [x] Add English word detection in correction prompt
- [x] Bite-sized correction chips under user messages
- [x] Correction stepper on summary page (step through one at a time, then full list)
- [x] Phrase selection translation (highlight multiple words to translate together)
- [x] MCQ infinite loop fix (conversations now increment `cards_answered`)
- [x] MCQ quality: improved AI prompt to avoid ambiguous "Which is correct?" questions
- [x] MCQ quality: added post-generation validation (`_validate_mcq`)
- [x] "Refresh Questions" button on Concepts page to clear AI MCQ cache
- [x] Conversation "Done" button: fallback `<a>` tag + error handling on summary endpoint
- [x] Concept Expansion Phase 1 — A1 gaps filled (possessive_adjectives, demonstratives, plurals, numbers_21_100, muy_mucho, frequency_adverbs, weather_seasons, clothing_vocab, body_parts, places_in_town, professions)
- [x] Concept Expansion Phase 2 — A2 grammar (reflexive_verbs, direct/indirect_object_pronouns, present_perfect, preterite_regular/irregular, imperfect_intro, comparatives, tener_que, estar_gerund, poder_infinitive, por_vs_para, conjunctions, conditional_politeness, imperative_basic)
- [x] Concept Expansion Phase 3 — A2 communicative vocab (shopping, health_doctor, travel_transport, hobbies_free_time, house_rooms, my_city)
- [x] Accelerated word tracking — harvest vocabulary from conversations (all user-produced Spanish words tracked automatically), word tap tracking (taps during conversation recorded as learning signals), smart word lifecycle (conversation words skip intro, enter as 'practicing'; tapped words enter as 'unseen')

## Up Next

### Persona System & Conversations

See `DESIGN_IDEAS.md` for full design thinking. Build order below follows the dependency chain. **Prompt ready: `PROMPT_PERSONAS.md`**

**Step 1 — Persona data layer + files**
- [ ] `personas` DB table: id, slug, name, soul_file_path, created_at
- [ ] Persona YAML files in `data/personas/` (marta.yaml, diego.yaml, abuela_rosa.yaml, luis.yaml) defining: identity, personality, conversation style, interest weights, vocab level, system prompt template
- [ ] `personas.py` module: load persona YAML, build dynamic system prompt with memory injection slots

**Step 2 — Refactor conversation engine to use personas**
- [ ] Refactor `conversation.py` to accept a persona object instead of hardcoded Marta
- [ ] System prompt built from persona YAML + injected memories + user profile
- [ ] Persona selection in `select_next_card()` for conversation injection — weighted by engagement scores (neutral start)

**Step 3 — Post-conversation evaluation (the hub)**
- [ ] `evaluation.py` module: single LLM call after each conversation that extracts:
  - Concepts demonstrated (with correct/error counts) → feeds BKT with boosted weight (production > recognition)
  - Vocabulary used → feeds words table
  - User facts to remember → feeds user_profile
  - Persona-specific observations → feeds persona_memories
  - Engagement quality assessment (soft signal)
- [ ] Wire into conversation summary flow (replace or augment current `generate_summary()`)

**Step 4 — Memory system**
- [ ] `persona_memories` table: persona_id, memory_text, conversation_id, importance_score, created_at. Capped at ~20 per persona, prune oldest/least-important.
- [ ] `user_profile` table: key, value, source (conversation_id), confidence, created_at. Shared across personas.
- [ ] Memory injection into persona system prompts before each conversation

**Step 5 — Conversation enjoyment scoring**
- [ ] Compute enjoyment score after each conversation: message_length (0.35), completion_ratio (0.25), no_early_exit (0.20), response_time (0.10), engagement_quality from LLM (0.10)
- [ ] `persona_engagement` table: persona_id, topic_id, conversation_count, avg_enjoyment_score, avg_message_length, avg_turns, early_exit_rate, last_conversation_at
- [ ] Persona rotation weighted by engagement scores + novelty bonus (TikTok-style algorithm)

**Step 6 — Conversation types**
- [ ] Implement conversation type selection: general chat (~50%), role play (~20%), concept-required (~15%), tutor (~15%), story comprehension (~10% — see below)
- [ ] Conversation type instruction injected into persona system prompt
- [ ] Type-aware post-conversation evaluation (concept-required gets pass/fail on target concept)

**Step 7 — Adaptive placement**
- [ ] Placement conversation mode: persona probes increasing complexity on first session
- [ ] Post-placement evaluation mass-unlocks concepts, sets initial CEFR dimension estimates
- [ ] Onboarding flow: 2-3 quick questions → placement conversation → calibrated concept graph

### Word-Level Tracking (remaining items)

- [ ] **Seed core vocabulary** — Pre-populate words for existing concepts with emojis AND topic tags. Core words (greetings, numbers, pronouns) have no topic. Domain words get tagged (cancha→sports, cocina→food). See DESIGN_IDEAS.md "Interest-driven vocabulary" for the tiering model (core / functional / deep).
- [ ] **Interest-driven word prioritization** — Word intro cards prioritize words from high-interest topics. If user loves basketball (interest score 0.9), basketball words surface before photography words (interest score 0.2).
- [ ] **Word-aware MCQ generation** — Tell the AI prompt which words the user knows, so distractors use known vocabulary and don't accidentally test unknown words

### New Card Types

Currently: teach, MCQ, conversation. Add variety to keep sessions engaging.

- [ ] **Story comprehension card** — Persona tells a short story (3-5 sentences) using target grammar, then 2-3 comprehension MCQs. Tests reading comprehension without production. Persona personality flavors the story. Variations: retell mode, fill-in-the-story, continuing the story. See DESIGN_IDEAS.md "Story Comprehension Card".
- [ ] **Fill-in-the-blank card** — Full sentence with one word blanked, 4 choices. Context constrains the answer. E.g. "Ella ___ alta." → es/está/son/están. Different from MCQ because it's inline and tests reading comprehension in context.
- [ ] **Match card** — Show 4-5 Spanish words on left, English (or emoji) on right, drag/tap to match pairs. Pure frontend, no AI needed. Great break from MCQs. Good for vocab reinforcement.
- [ ] **Sentence builder card** — Scrambled words, arrange in correct order. Tests word order / grammar understanding differently. E.g. [gusta / me / la / música] → "Me gusta la música."
- [ ] **Listening card** (future) — Play a sentence via TTS, pick the translation or type what you heard. Browser SpeechSynthesis API is free. Start with "listen and choose" before "listen and type."
- [ ] **Image/emoji association card** — Show an emoji or simple image, pick the Spanish word. Fast, visual, low-stakes. Good for vocab drilling.

### Other improvements

- [ ] **Bite-sized corrections quality pass** — The corrections are better with `gpt-4o` but could still be more granular. Test with real conversations and tune the prompt if needed.
- [ ] **Summary page: step-through UX polish** — Animate transitions between correction cards, maybe add swipe support on mobile.

## Ideas / Future

See also: `DESIGN_IDEAS.md` for bigger-picture thinking (persona system, memory, conversation design, AI backend research).

- [ ] **Conversation design overhaul** — Move beyond Q&A format. Role-play, storytelling, games, mutual exchange. Research what makes conversations fun.
- [ ] **AI backend research** — LLM vs fine-tuning vs self-hosted. Cost analysis, personality consistency benchmarks.
- [ ] **"More info" on word tooltip** — Tap a word, see translation, then option to drill deeper (conjugation table, example sentences, related words).
- [ ] **Spaced repetition for conversation corrections** — Feed corrections back into the MCQ system so words you got wrong in conversation show up as flashcards later.
- [ ] **Mobile UX audit** — Test the whole flow on phone. Chat bubbles, tooltip positioning, phrase selection on touch.
- [ ] **Progress dashboard improvements** — Graphs over time, streak calendar, weekly goals.
- [ ] **Audio / pronunciation** — Text-to-speech on AI messages, or speech-to-text for user input.
- [ ] **Video comprehension cards** — Short video clips with questions. Content sourcing is the hard part. Could start with animated text scenes as a stepping stone.
