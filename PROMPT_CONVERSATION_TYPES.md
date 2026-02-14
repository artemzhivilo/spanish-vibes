# Conversation Types — Implementation Prompt

## Context

Read `PROMPT.md` for full project context, `DESIGN_IDEAS.md` sections "Conversation Types" and "Story Comprehension Card" for design rationale. Read `BACKLOG.md` Step 6.

**The goal:** Instead of every conversation being the same free-form chat, introduce five conversation types that create structural variety and enable targeted diagnostics. The system picks the type based on the learner's state, and the type instruction gets injected into the persona's system prompt. The post-conversation evaluation is type-aware.

**Dependencies:** Assumes personas (Steps 1+2), evaluation (Step 3), memory (Step 4), and enjoyment scoring (Step 5) are implemented.

## The five conversation types

1. **General Chat** (~50% default) — Free-form conversation, no particular goal. The baseline "hanging out" mode. Best for comfort, interest discovery, memory building.

2. **Role Play** (~20%) — Scenario-based. Persona plays a role (waiter, stranger, interviewer). User plays themselves navigating the situation. Good for fluency, real-world vocab.

3. **Concept-Required** (~15%) — Free-form BUT the user must use a specific grammar concept. Persona steers toward situations that require it. Evaluation checks pass/fail on target concept. Solves the "avoided structure" problem.

4. **Tutor** (~15%) — Persona explicitly teaches a concept through conversation. Still conversational, not a lecture. Good for concepts the user is struggling with.

5. **Story Comprehension** (~10%, steals from others) — Persona tells a short story (3-5 sentences), then 2-3 comprehension MCQs. Tests reading comprehension without production. This is a different card structure than the other four (it's not a back-and-forth chat).

## What to build

### 1. Conversation type selection function

Add to `flow.py` or a new `conversation_types.py` module:

```python
def select_conversation_type(
    concept_id: str,
    session_id: int,
) -> tuple[str, str | None]:
    """Select a conversation type based on learner state.

    Returns (conversation_type, target_concept_id_or_none).
    conversation_type is one of: "general_chat", "role_play", "concept_required", "tutor", "story_comprehension"
    target_concept_id is only set for concept_required and tutor types.
    """
```

**Selection logic:**

Start with weighted random as the base, then override based on learner state:

```python
# Base weights
weights = {
    "general_chat": 0.45,
    "role_play": 0.20,
    "concept_required": 0.15,
    "tutor": 0.10,
    "story_comprehension": 0.10,
}
```

**Override rules (check in order, first match wins):**

1. **Stuck concept detected** → force `concept_required`
   - A concept is "stuck" if: p_mastery > 0.5 (knows it in MCQs) BUT it's never appeared in `concepts_demonstrated` from evaluation (never produced it in conversation), AND n_attempts >= 5
   - For the initial implementation, a simpler heuristic: concepts with high MCQ accuracy but low overall mastery, or concepts that have been attempted many times without reaching mastery
   - Set `target_concept_id` to the stuck concept

2. **Recently introduced concept** (teach_shown within last 3 sessions, n_attempts < 3) → boost `tutor` weight to 0.40
   - Set `target_concept_id` to the new concept

3. **Low engagement trend** (last 2 conversations had enjoyment < 0.3) → boost `general_chat` to 0.60 and `role_play` to 0.25, reduce `tutor` and `concept_required`

4. **Otherwise** → use base weights with weighted random selection

For the initial implementation, keep it simple: use base weights with random selection, plus the stuck concept override. The other overrides can be added iteratively.

### 2. Conversation type instructions

Create a mapping of type → prompt instruction that gets injected into the persona system prompt. Add to `conversation_types.py` or `conversation.py`:

```python
CONVERSATION_TYPE_INSTRUCTIONS = {
    "general_chat": (
        "CONVERSATION MODE: General Chat\n"
        "Have a natural, free-form conversation. Talk about whatever interests you both. "
        "Share your own stories and opinions. Ask follow-up questions. "
        "There's no specific learning goal — just enjoy chatting in Spanish."
    ),
    "role_play": (
        "CONVERSATION MODE: Role Play\n"
        "You are playing a specific role in a scenario. Stay in character for the scenario. "
        "Guide the learner through the situation naturally — don't break the scene to teach. "
        "The scenario will be described below.\n\n"
        "SCENARIO: {scenario}"
    ),
    "concept_required": (
        "CONVERSATION MODE: Concept Practice\n"
        "Have a natural conversation, but steer it so the learner NEEDS to use {concept_name}. "
        "Don't tell them what to practice — just create situations where the concept is needed. "
        "Ask questions that require {concept_name} in the answer. "
        "If they avoid it, gently redirect: ask a more specific question that demands it."
    ),
    "tutor": (
        "CONVERSATION MODE: Tutor\n"
        "Today you're helping the learner with {concept_name}. "
        "Teach through examples and natural conversation, NOT lectures. "
        "Give a brief example, ask them to try, then gently correct. "
        "Use your personality — make it fun, not like a textbook. "
        "Celebrate their attempts even when imperfect."
    ),
    "story_comprehension": None,  # Handled differently — not a chat conversation
}
```

**Role play scenarios** — create a bank of scenarios per topic/persona combo:

```python
ROLE_PLAY_SCENARIOS = {
    "food_cooking": [
        "You are a waiter at a tapas restaurant in Madrid. The learner is a customer ordering dinner. Suggest dishes, ask about preferences, take their order.",
        "You are a vendor at a market selling fresh fruit and vegetables. The learner wants to buy ingredients for a recipe. Negotiate prices, suggest alternatives.",
    ],
    "travel": [
        "You are a stranger on the street. The learner is lost and asking for directions to the train station. Give directions using landmarks.",
        "You are a hotel receptionist. The learner is checking in. Ask for their reservation, explain breakfast hours, recommend local attractions.",
    ],
    "sports": [
        "You are a ticket seller at a football stadium. The learner wants to buy tickets for tonight's match. Discuss seating options and prices.",
        "You are a fitness trainer at a gym. The learner is signing up. Ask about their fitness goals, explain the schedule.",
    ],
    # Add more per topic. Fallback: generate one with LLM if no pre-built scenario matches.
}
```

Keep the scenario bank small to start (2-3 per common topic). If no pre-built scenario matches the topic, generate one on the fly with a quick LLM call, OR fall back to general_chat.

### 3. Wire type selection into conversation start

In `flow_routes.py` `conversation_start` endpoint, after persona selection and before `generate_opener()`:

```python
from .conversation_types import select_conversation_type, get_type_instruction, select_role_play_scenario

# Select conversation type
conv_type, target_concept = select_conversation_type(concept_id, session_id)

# If concept_required or tutor, the target concept might differ from the card's concept
effective_concept = target_concept or concept_id

# Get the type instruction to inject into the persona prompt
type_instruction = get_type_instruction(conv_type, concept_id=effective_concept, topic=topic)

# Build the full persona prompt with memories + type instruction
persona_prompt = get_persona_prompt(
    persona,
    persona_memories=memories,
    user_facts=user_facts,
)
# Append type instruction
if type_instruction:
    persona_prompt += f"\n\n{type_instruction}"
```

For **story comprehension**, this is a different flow entirely — it doesn't use `generate_opener()` and `respond_to_user()`. Instead:
- Generate a story + comprehension questions in one LLM call
- Render as a story card (new template partial), not a chat UI
- User answers the MCQs, results feed into BKT and word tracking
- See section 6 below for details

### 4. Add `conversation_type` column to `flow_conversations`

In `db.py`:

```sql
-- In the ALTER TABLE section for flow_conversations:
if "conversation_type" not in conv_cols:
    connection.execute("ALTER TABLE flow_conversations ADD COLUMN conversation_type TEXT NOT NULL DEFAULT 'general_chat'")
```

Store the type when creating the conversation record in `conversation_start`.

### 5. Type-aware post-conversation evaluation

Modify the evaluation prompt in `evaluation.py` to include the conversation type:

```python
# Add to the system prompt for evaluate_conversation():
f"CONVERSATION TYPE: {conversation_type}\n"
```

Add type-specific extraction to the evaluation:

```python
# Add to the evaluation JSON schema:
"concept_required_result": {
    "target_concept": "preterite_regular",
    "produced": true,
    "correct_uses": 2,
    "incorrect_uses": 1
}
```

For **concept-required** conversations:
- If the user produced the target concept correctly → strong positive BKT update (boosted weight, even more than regular conversation evidence)
- If the user failed to produce it at all → negative signal. Don't penalize BKT harshly, but flag the concept as "avoided" for future targeting
- If the user produced it incorrectly → normal negative BKT update

For **tutor** conversations:
- Evaluate whether the user demonstrated understanding by the end
- More forgiving — errors are expected since they're learning something new

For **general_chat** and **role_play**:
- Standard evaluation — extract whatever concepts appeared naturally

### 6. Story comprehension card (new card type)

This is different from the other conversation types because it's not a back-and-forth chat. It's closer to an MCQ card with a story preamble.

**a) Story generation function** (add to `flow_ai.py` or a new `stories.py`):

```python
def generate_story_card(
    concept_id: str,
    topic: str,
    difficulty: int,
    persona_prompt: str,
    persona_name: str,
) -> dict:
    """Generate a short story + comprehension questions.

    Returns:
    {
        "story": "Ayer, Diego fue al estadio con sus amigos. Compraron entradas...",
        "questions": [
            {
                "question": "¿Adónde fue Diego?",
                "correct_answer": "Al estadio",
                "options": ["Al estadio", "Al cine", "A la playa", "Al mercado"]
            },
            {
                "question": "¿Con quién fue?",
                "correct_answer": "Con sus amigos",
                "options": ["Con sus amigos", "Con su madre", "Solo", "Con su perro"]
            }
        ]
    }
    """
```

LLM prompt should:
- Generate a 3-5 sentence story in Spanish using the target grammar concept
- Write in the persona's voice/style
- Create 2-3 comprehension MCQs with 4 options each
- Scale difficulty: A1 = simple sentences + yes/no or factual questions, A2 = more complex + inference questions

**b) New template partial** `templates/partials/flow_story_card.html`:

```html
<!-- Story text with tappable words -->
<div class="story-text">
  {{ story | tappable | safe }}
</div>

<!-- Comprehension questions (rendered as MCQs) -->
<div class="story-questions">
  {% for q in questions %}
    <!-- Similar to existing MCQ card UI but within the story card -->
  {% endfor %}
</div>
```

**c) Wire into card selection:**

When `select_conversation_type()` returns `"story_comprehension"`:
- Don't start a normal conversation
- Instead call `generate_story_card()` and render the story card template
- Story card answers feed into BKT (comprehension evidence) and word tracking (words in the story text get harvested)

**d) Story card flow in `flow_routes.py`:**

Either:
- Handle story_comprehension as a special case in `conversation_start` that redirects to a story card render, OR
- Add a separate `/flow/story-card/start` endpoint

The second option is cleaner since the story card has a fundamentally different UI (not a chat).

### 7. Update `flow.py` card selection

When `select_next_card()` decides it's time for a conversation, it should:
1. Call `select_conversation_type()` to pick the type
2. If `story_comprehension` → return a `FlowCardContext` with `card_type="story_comprehension"`
3. Otherwise → return the existing `card_type="conversation"` with the type stored in context

Add `conversation_type` to `FlowCardContext` (or pass it through `interest_topics` or a new field).

## What NOT to build yet

- No adaptive type selection based on engagement trends (just use base weights + stuck concept override for now)
- No conversation type history tracking (which types have been used recently) — add later for variety enforcement
- No user preference for conversation types (they can't pick — system decides, like TikTok)
- No complex scenario generation (use the pre-built bank, fall back to general_chat if no match)

## Key design decisions

- **System picks the type** — users never choose. This is the TikTok philosophy: the algorithm decides what's best.
- **Story comprehension is a card, not a conversation** — it has a fundamentally different UI (read + answer, not chat). Treat it as a new card type.
- **Concept-required is the diagnostic tool** — this is the strongest evidence for concept mastery because it tests spontaneous production in context. Weight BKT updates accordingly.
- **Keep the scenario bank small** — 2-3 per topic to start. Quality over quantity. Can always add more.
- **Fallback to general_chat** — if anything goes wrong with type selection or scenario loading, just do a general chat. It always works.

## Files to create

1. `src/spanish_vibes/conversation_types.py` — Type selection, type instructions, role play scenario bank
2. `templates/partials/flow_story_card.html` — Story comprehension card template

## Files to modify

1. `src/spanish_vibes/db.py` — Add `conversation_type` column to `flow_conversations`
2. `src/spanish_vibes/flow_routes.py` — Wire type selection into `conversation_start`, add story card endpoint
3. `src/spanish_vibes/flow_ai.py` — Add `generate_story_card()` function
4. `src/spanish_vibes/evaluation.py` — Make evaluation type-aware (concept_required pass/fail)
5. `src/spanish_vibes/flow.py` — Update `select_next_card()` to handle story_comprehension card type
6. `src/spanish_vibes/models.py` — Add `conversation_type` to `FlowCardContext` if needed
7. `src/spanish_vibes/personas.py` — Update `get_persona_prompt()` to accept type instruction (or just append in the route)
8. `templates/partials/flow_card.html` — Add story_comprehension card rendering

## Testing

- Verify type selection returns valid types with roughly correct distribution (run 100 selections)
- Verify stuck concept detection triggers concept_required
- Verify type instruction appears in the persona system prompt
- Verify conversation_type is stored in flow_conversations
- Verify role play conversations use the scenario in the prompt
- Verify concept_required evaluation includes pass/fail on target concept
- Verify story card generates valid story + questions
- Verify story card MCQ answers feed into BKT
- Verify fallback to general_chat works when errors occur
- Verify existing conversation flow still works (general_chat is backward compatible)
