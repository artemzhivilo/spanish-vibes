# Spanish Vibes — Backlog

## Bugs

(none currently)

## Recently Done

- [x] Upgrade conversation corrections to `gpt-4o` (from `gpt-4o-mini`)
- [x] Add English word detection in correction prompt
- [x] Bite-sized correction chips under user messages
- [x] Correction stepper on summary page (step through one at a time, then full list)
- [x] Phrase selection translation (highlight multiple words to translate together)
- [x] MCQ infinite loop fix (conversations now increment `cards_answered`)

## Up Next

### Concept Expansion (A1 completion + A2)

Current state: 29 concepts across 6 tiers, covering basic A1. Need ~30 more to fully cover A1 and start A2.
CEFR references: Instituto Cervantes Plan Curricular, DELE A1/A2 syllabus, Kwiziq/Inhispania course maps.

**Phase 1 — Fill A1 gaps (Tiers 2-5)** — Add to `data/concepts.yaml`, run `seed_concepts_to_db()`

- [ ] `possessive_adjectives` (Tier 3) — mi, tu, su, nuestro. Prereqs: nouns_gender
- [ ] `demonstratives` (Tier 3) — este/ese/aquel + agreement. Prereqs: nouns_gender
- [ ] `plurals` (Tier 3) — forming plurals (-s, -es, -ces). Prereqs: nouns_gender
- [ ] `numbers_21_100` (Tier 2) — veintiuno to cien. Prereqs: numbers_1_20
- [ ] `muy_mucho` (Tier 4) — muy + adjective, mucho + noun. Prereqs: adjective_agreement
- [ ] `frequency_adverbs` (Tier 4) — siempre, a veces, nunca, todos los días. Prereqs: present_tense_ar
- [ ] `weather_seasons` (Tier 3) — hace frío/calor, llueve, nieva + seasons. Prereqs: hay
- [ ] `clothing_vocab` (Tier 2) — la camisa, los zapatos, etc. Prereqs: greetings
- [ ] `body_parts` (Tier 2) — la cabeza, el brazo, etc. Prereqs: greetings
- [ ] `places_in_town` (Tier 3) — el banco, la tienda, el hospital, la escuela. Prereqs: articles_definite
- [ ] `professions` (Tier 3) — profesor, médico, etc + ser. Prereqs: ser_present

**Phase 2 — A2 grammar (Tiers 6-8)**

- [ ] `reflexive_verbs` (Tier 6) — llamarse, levantarse, ducharse, vestirse. Prereqs: present_tense_ar
- [ ] `direct_object_pronouns` (Tier 7) — lo, la, los, las. Prereqs: present_tense_ar, present_tense_er_ir
- [ ] `indirect_object_pronouns` (Tier 7) — me, te, le, nos, les. Prereqs: gustar
- [ ] `present_perfect` (Tier 7) — he/has/ha + past participle. Prereqs: present_tense_ar, present_tense_er_ir
- [ ] `preterite_regular` (Tier 7) — -ar/-er/-ir regular preterite endings. Prereqs: present_tense_ar, present_tense_er_ir
- [ ] `preterite_irregular` (Tier 8) — fui, hice, tuve, etc. Prereqs: preterite_regular
- [ ] `imperfect_intro` (Tier 8) — -aba/-ía endings, habitual past. Prereqs: preterite_regular
- [ ] `comparatives` (Tier 7) — más/menos...que, tan...como, mejor/peor. Prereqs: adjective_agreement
- [ ] `tener_que_hay_que` (Tier 6) — obligation: tener que, hay que, deber. Prereqs: tener_present
- [ ] `estar_gerund` (Tier 6) — estar + -ando/-iendo (present progressive). Prereqs: estar_present
- [ ] `poder_infinitive` (Tier 6) — puedo/puedes/puede + verb. Prereqs: present_tense_er_ir
- [ ] `por_vs_para` (Tier 7) — core uses. Prereqs: basic_prepositions
- [ ] `conjunctions` (Tier 6) — pero, porque, cuando, si, y, o. Prereqs: present_tense_ar
- [ ] `conditional_politeness` (Tier 8) — quisiera, podría, me gustaría. Prereqs: gustar, poder_infinitive
- [ ] `imperative_basic` (Tier 8) — tú commands affirmative. Prereqs: present_tense_ar

**Phase 3 — A2 communicative vocab (Tiers 6-8)**

- [ ] `shopping` (Tier 7) — ¿Cuánto cuesta?, comprar, pagar, la tienda. Prereqs: numbers_21_100, querer
- [ ] `health_doctor` (Tier 7) — me duele, tengo fiebre, el médico. Prereqs: body_parts, tener_present
- [ ] `travel_transport` (Tier 7) — el tren, el avión, el billete, viajar. Prereqs: ir_a, basic_prepositions
- [ ] `hobbies_free_time` (Tier 6) — deportes, leer, nadar, jugar. Prereqs: gustar
- [ ] `house_rooms` (Tier 5) — la cocina, el baño, el dormitorio. Prereqs: articles_definite, basic_prepositions
- [ ] `my_city` (Tier 7) — describing where you live. Prereqs: hay, estar_present, places_in_town

### Other improvements

- [ ] **Bite-sized corrections quality pass** — The corrections are better with `gpt-4o` but could still be more granular. Test with real conversations and tune the prompt if needed.
- [ ] **Summary page: step-through UX polish** — Animate transitions between correction cards, maybe add swipe support on mobile.

## Ideas / Future

- [ ] **"More info" on word tooltip** — Tap a word, see translation, then option to drill deeper (conjugation table, example sentences, related words). Parked for now.
- [ ] **Spaced repetition for conversation corrections** — Feed corrections back into the MCQ system so words you got wrong in conversation show up as flashcards later.
- [ ] **Mobile UX audit** — Test the whole flow on phone. Chat bubbles, tooltip positioning, phrase selection on touch.
- [ ] **Conversation variety** — More persona styles beyond Marta? Different conversation formats (ordering food, asking directions, etc)?
- [ ] **Progress dashboard improvements** — Graphs over time, streak calendar, weekly goals.
- [ ] **Audio / pronunciation** — Text-to-speech on AI messages, or speech-to-text for user input.
