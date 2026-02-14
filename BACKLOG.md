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
- [x] Accelerated word tracking — harvest vocabulary from conversations, word tap tracking, smart word lifecycle
- [x] Persona data layer — 4 personas (Marta, Diego, Abuela Rosa, Luis) with YAML soul files, `personas.py` module with loading, prompt building, memory injection
- [x] Conversation engine refactored for personas — system prompt from YAML + memories + user profile, engagement-weighted persona selection
- [x] Post-conversation evaluation — `evaluation.py` with GPT-4o call extracting concepts demonstrated, vocabulary used, user facts, persona observations, engagement quality, estimated CEFR
- [x] Memory system — `persona_memories` and `user_profile` tables, store/retrieve/prune functions, injected into persona system prompts
- [x] Conversation enjoyment scoring — 5-factor weighted score (message_length, completion_ratio, no_early_exit, response_time, engagement_quality), `persona_engagement` table, persona rotation weighted by engagement + novelty
- [x] Conversation types — 6 types (general_chat, role_play, concept_required, tutor, story_comprehension, placement) with weighted selection, type-specific instruction injection, role-play scenarios
- [x] Adaptive placement — placement conversation mode, post-placement mass-unlock, onboarding flow with interest questions
- [x] Adaptive difficulty — `get_user_level()` computed from BKT tier mastery, difficulty-aware MCQ selection, CEFR-based conversation scaffolding
- [x] Interest tracking fix — conversations generate interest signals (MCQs don't), topic matching via `CONCEPT_TOPIC_MAP`, EMA scoring with time decay
- [x] Conversation loop fix — `cards_answered` incremented at conversation start, not just summary completion
- [x] Dev tools fix — dev panel layout and functionality

## Up Next

### Word System

The word pipeline is starved: only 16 seed words across 4 concepts, while 48 concepts exist. Without words, word intro/practice/match cards can't appear.

- [ ] **Seed vocabulary for all concepts** — Pre-populate words for all 48 concepts with Spanish, English, emoji, and example sentences. Core words (greetings, numbers, pronouns) have no topic tag. Domain words get topic tags (cancha→sports, cocina→food-cooking). Target: 8-12 words per concept, ~400-500 total words.
- [ ] **Interest-driven word prioritization** — Word intro cards prioritize words from high-interest topics. If user loves basketball (interest score 0.9), basketball words surface before photography words (interest score 0.2). Requires topic_id on words table + changes to `get_intro_candidate()`.
- [ ] **Word-aware MCQ generation** — Tell the AI prompt which words the user knows, so distractors use known vocabulary and don't accidentally test unknown words.
- [ ] **Word tap sentence bug fix** — Only count single-word selections as word tap signals.

### New Card Types

Currently: teach, MCQ, conversation. Add variety to keep sessions engaging.

- [ ] **Story comprehension card** — Persona tells a short story (3-5 sentences) using target grammar, then 2-3 comprehension MCQs. UI scaffolding exists, needs generation logic.
- [ ] **Fill-in-the-blank card** — Full sentence with one word blanked, 4 choices. Context constrains the answer. Different from MCQ because it's inline and tests reading comprehension in context.
- [ ] **Sentence builder card** — Scrambled words, arrange in correct order. Tests word order / grammar understanding.
- [ ] **Listening card** (future) — Play a sentence via TTS, pick the translation or type what you heard. Browser SpeechSynthesis API is free.
- [ ] **Image/emoji association card** — Show an emoji or simple image, pick the Spanish word. Fast, visual, low-stakes.

### Other improvements

- [ ] **Bite-sized corrections quality pass** — Test with real conversations and tune the prompt if needed.
- [ ] **Summary page: step-through UX polish** — Animate transitions between correction cards, maybe add swipe support on mobile.

## Ideas / Future

See also: `DESIGN_IDEAS.md` for bigger-picture thinking.

- [ ] **"More info" on word tooltip** — Tap a word, see translation, then option to drill deeper (conjugation table, example sentences, related words).
- [ ] **Spaced repetition for conversation corrections** — Feed corrections back into the MCQ system so words you got wrong in conversation show up as flashcards later.
- [ ] **Mobile UX audit** — Test the whole flow on phone. Chat bubbles, tooltip positioning, phrase selection on touch.
- [ ] **Progress dashboard improvements** — Graphs over time, streak calendar, weekly goals.
- [ ] **Audio / pronunciation** — Text-to-speech on AI messages, or speech-to-text for user input.
- [ ] **AI backend research** — LLM vs fine-tuning vs self-hosted. Cost analysis, personality consistency benchmarks.
