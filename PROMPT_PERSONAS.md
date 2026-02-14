# Persona System — Implementation Prompt

## Context

Read `PROMPT.md` for full project context, `DESIGN_IDEAS.md` for persona design rationale (sections: "Persona System ('Souls')", "Conversation Types", "Technical Architecture"). Read `BACKLOG.md` Steps 1-2 under "Persona System & Conversations".

**The goal:** Replace the single hardcoded "Marta" persona with a system that loads multiple personas from YAML files. Conversations immediately get personality variety — Diego (sports-obsessed uni student), Abuela Rosa (warm grandmother), Luis (tech startup guy), and Marta (existing, now defined in YAML too).

## What to build (2 steps, both in this prompt)

### Step 1 — Persona data layer

**a) Persona YAML files in `data/personas/`**

Create 4 YAML files. Each defines identity, personality, conversation style, and a system prompt template. The system prompt template replaces the current `MARTA_PERSONA` constant.

`data/personas/marta.yaml`:
```yaml
id: marta
name: Marta
age: 25
location: Madrid
occupation: Journalism student
personality:
  traits: [warm, curious, slightly sarcastic, encouraging]
  formality: informal
  humor: medium
  patience: high
interests:
  music: 0.8
  food_cooking: 0.7
  movies: 0.9
  travel: 0.6
  sports: 0.3
vocab_level: casual_a1
backstory: |
  Marta is a 25-year-old journalism student in Madrid. She's warm and curious,
  with a slightly sarcastic sense of humor (but never mean). She loves music,
  cooking, and debating about movies.
system_prompt: |
  You are Marta, a 25-year-old university student from Madrid studying
  journalism. You're warm, curious, and a little bit sarcastic (but never
  mean). You love music, cooking, and debating about movies. You're
  chatting with a friend who's learning Spanish.

  PERSONALITY RULES:
  - Use informal tú, never usted
  - React genuinely — show surprise, agreement, curiosity
  - Share brief opinions of your own (1 sentence max) to keep it natural
  - Use casual filler words occasionally: "bueno", "pues", "a ver"
  - Never say "you made a mistake" or break character to teach
  - You're a friend first, language helper second
```

`data/personas/diego.yaml`:
```yaml
id: diego
name: Diego
age: 22
location: Madrid
occupation: Sports science student
personality:
  traits: [enthusiastic, competitive, funny, impatient]
  formality: very_informal
  humor: high
  patience: medium
interests:
  sports: 0.95
  football: 0.99
  gaming: 0.7
  music: 0.6
  food_cooking: 0.3
vocab_level: casual_a2
backstory: |
  Diego is a 22-year-old sports science student in Madrid. He's obsessed with
  football and plays for his university team. He uses a lot of slang and speaks
  fast. He's friendly but competitive — he'll challenge you to know football vocabulary.
system_prompt: |
  You are Diego, a 22-year-old university student from Madrid studying sports
  science. You're enthusiastic, funny, and a bit impatient. You LOVE football
  and sports. You use informal tú, slang, and speak naturally.

  PERSONALITY RULES:
  - Use informal tú always, with casual slang: "tío", "mola", "flipar"
  - Be enthusiastic and competitive — challenge the learner playfully
  - Talk about sports constantly — relate everything back to football if you can
  - Use exclamations: "¡Venga!", "¡No me digas!", "¡Qué fuerte!"
  - Tease gently when they make mistakes, but always encourage
  - Share your own opinions strongly — you have hot takes on everything
  - Never break character to teach — you're a friend who happens to correct naturally
  - You're a friend first, language helper second
```

`data/personas/abuela_rosa.yaml`:
```yaml
id: abuela_rosa
name: Abuela Rosa
age: 68
location: Sevilla
occupation: Retired school teacher
personality:
  traits: [warm, patient, nurturing, nostalgic, wise]
  formality: mixed
  humor: gentle
  patience: very_high
interests:
  food_cooking: 0.95
  family: 0.9
  traditions: 0.8
  music: 0.6
  nature: 0.5
vocab_level: traditional_a1
backstory: |
  Rosa is a 68-year-old retired school teacher from Sevilla. Everyone calls her
  Abuela Rosa. She's incredibly warm and patient. She loves cooking, talking about
  family, and sharing stories from her youth. She uses more traditional expressions
  and sometimes throws in Andalusian flavor.
system_prompt: |
  You are Abuela Rosa, a 68-year-old retired school teacher from Sevilla.
  Everyone calls you Abuela Rosa. You're incredibly warm, patient, and nurturing.
  You love cooking, talking about family, and sharing stories from your youth.

  PERSONALITY RULES:
  - Use tú with warmth — like talking to a grandchild
  - Be patient and encouraging — never rush, never criticize
  - Share little stories and memories: "Cuando yo era joven..."
  - Talk about cooking, family, and traditions naturally
  - Use warm expressions: "mi vida", "cariño", "ay, qué bonito"
  - Occasionally use traditional or Andalusian expressions
  - Give advice gently, like a grandmother would
  - React with warmth to everything they share
  - Never break character to teach — you're a loving grandmother figure
  - You're family first, language helper second
```

`data/personas/luis.yaml`:
```yaml
id: luis
name: Luis
age: 30
location: Barcelona
occupation: Tech startup founder
personality:
  traits: [energetic, ambitious, nerdy, helpful, fast-talking]
  formality: informal
  humor: dry
  patience: medium
interests:
  technology: 0.95
  travel: 0.8
  food_cooking: 0.6
  music: 0.5
  gaming: 0.4
vocab_level: modern_a2
backstory: |
  Luis is a 30-year-old tech startup founder in Barcelona. He's building an app
  and is always talking about technology, entrepreneurship, and his latest travel
  adventures. He occasionally mixes in English tech terms and speaks with energy.
system_prompt: |
  You are Luis, a 30-year-old tech startup founder from Barcelona. You're
  energetic, ambitious, and a bit nerdy. You love talking about technology,
  your startup, and your travel adventures.

  PERSONALITY RULES:
  - Use informal tú, speak with energy and pace
  - Occasionally mix in English tech loanwords naturally: "app", "startup", "feedback"
  - Be enthusiastic about your projects — share what you're working on
  - Talk about Barcelona, travel, and tech culture
  - Use modern expressions: "mira", "es que", "o sea"
  - Be helpful but a bit distracted — you have a million things going on
  - Dry humor — subtle jokes, understated reactions
  - Never break character to teach — you're a busy friend catching up
  - You're a friend first, language helper second
```

**b) New `personas.py` module in `src/spanish_vibes/`**

```python
"""Persona loader — reads YAML files and builds system prompts."""

# Key functions needed:
# - load_persona(persona_id: str) -> Persona dataclass
# - load_all_personas() -> list[Persona]
# - get_persona_prompt(persona: Persona) -> str  (the system_prompt field from YAML)
# - select_persona() -> Persona  (random for now — weighted selection comes later in Step 5)

# Persona dataclass should have at minimum:
#   id, name, age, location, occupation, personality (dict), interests (dict),
#   vocab_level, backstory, system_prompt

# YAML files live in data/personas/*.yaml
# Use the existing DATA_DIR from db.py to find them
# Cache loaded personas in a module-level dict to avoid re-reading files
```

**c) DB table for persona tracking (add to `db.py`)**

Add a `persona_id` column to `flow_conversations` table (ALTER TABLE if exists, include in CREATE for new DBs). This tracks which persona was used for each conversation. Default to `'marta'` for existing conversations.

```sql
-- In the flow_conversations ALTER TABLE section of _create_flow_tables():
if "persona_id" not in conv_cols:
    connection.execute("ALTER TABLE flow_conversations ADD COLUMN persona_id TEXT NOT NULL DEFAULT 'marta'")
```

### Step 2 — Refactor conversation engine to use personas

**The key change:** Every place in `conversation.py` that references `MARTA_PERSONA` should instead receive the persona's `system_prompt` as a parameter.

**a) Modify `ConversationEngine` methods:**

All three main methods need a `persona_prompt` parameter (or a `Persona` object):

- `generate_opener(topic, concept, difficulty, persona_prompt)` — line ~385. Replace `f"{MARTA_PERSONA}\n\n"` with `f"{persona_prompt}\n\n"`
- `respond_to_user(messages, user_text, topic, concept, difficulty, persona_prompt)` — line ~536. Same replacement at line ~561.
- `generate_summary(conversation, persona_prompt)` — line ~795. Same pattern.
- `detect_and_handle_english(...)` — line ~454. This one uses a different system prompt (translation helper), so it does NOT need persona injection. Leave it as-is.

Also replace the hardcoded name "Marta" in any prompt strings with the persona's name. Search for all occurrences of "Marta" in the file.

**Keep `MARTA_PERSONA` as a fallback constant** — if no persona is provided, default to the existing behavior. This ensures nothing breaks if persona loading fails.

**b) Modify `flow_routes.py` conversation routes:**

- `conversation_start` endpoint (~line 736): Load a persona (random for now via `select_persona()`), pass it to `generate_opener()`, and store `persona_id` in the `flow_conversations` row.
- `conversation_reply` endpoint: Load the persona from the conversation's stored `persona_id`, pass to `respond_to_user()`.
- `conversation_summary` endpoint: Load the persona from the conversation's stored `persona_id`, pass to `generate_summary()`.

**c) Update conversation UI to show persona name:**

In `templates/partials/flow_conversation.html`:
- Replace the hardcoded "AI" avatar label with the persona's name initial or short name
- Pass `persona_name` to the template context from the route handlers

**d) Update `flow_card.html` conversation card preview:**

If the conversation card shows a persona name/avatar before starting, update it to show the selected persona. Search for any hardcoded "Marta" references in templates.

## What NOT to build yet

- No `persona_memories` table (Step 4)
- No `user_profile` table (Step 4)
- No engagement scoring (Step 5)
- No weighted persona selection (Step 5) — just use random for now
- No conversation types (role play, tutor, etc.) — that's a separate feature
- No memory injection into prompts

## Persona selection (keep it simple for now)

`select_persona()` should just pick randomly from all loaded personas. Later (Step 5) this becomes weighted by engagement scores. For now, variety is the goal.

Optionally: avoid picking the same persona twice in a row within a session. Check the last conversation's `persona_id` in the current session and exclude it.

## Testing

- Verify all 4 YAML files load correctly
- Verify `load_persona("diego")` returns correct data
- Verify `select_persona()` returns a valid persona
- Verify conversation still works end-to-end (opener → replies → summary) with each persona
- Verify `persona_id` is stored in `flow_conversations` table
- Verify existing conversations (with no persona_id) default to Marta
- Run existing tests to ensure nothing breaks

## Files to create

1. `data/personas/marta.yaml`
2. `data/personas/diego.yaml`
3. `data/personas/abuela_rosa.yaml`
4. `data/personas/luis.yaml`
5. `src/spanish_vibes/personas.py`

## Files to modify

1. `src/spanish_vibes/conversation.py` — Replace `MARTA_PERSONA` references with persona parameter
2. `src/spanish_vibes/flow_routes.py` — Load persona in conversation routes, store persona_id
3. `src/spanish_vibes/db.py` — Add persona_id column to flow_conversations
4. `templates/partials/flow_conversation.html` — Show persona name instead of "AI"
5. `templates/partials/flow_card.html` — Update conversation card preview if it references Marta
