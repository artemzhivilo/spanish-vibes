# Prompt: Conversation Engine v2

Feed this to Claude Code. It replaces the current conversation.py with a
research-backed redesign.

---

## Context

In the spanish-vibes FastAPI app (src/spanish_vibes/conversation.py), the
conversation engine currently makes TWO separate API calls per user turn:
`evaluate_response` (GPT-4o, expensive) and `generate_reply` (GPT-4o-mini).
These are disconnected — the reply doesn't use the evaluation. The whole
thing needs to be rebuilt as a single, well-engineered pipeline.

The conversation card is the most differentiating feature of this app.
It needs to feel like talking to a real person who happens to be helping
you learn Spanish, not like a grammar drill wearing a chat UI costume.

## What to change

### 1. Create a persona: Marta

The AI conversation partner needs a consistent character. Research shows
personas yield medium-to-large learning gains and reduce learner anxiety.

Define Marta's character at the top of conversation.py as a constant:

```python
MARTA_PERSONA = """
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
"""
```

### 2. Replace evaluate_response + generate_reply with single respond_to_user

Delete the separate `evaluate_response` and `generate_reply` methods.
Replace with a single method that does everything in ONE API call using
OpenAI Structured Outputs:

```python
@dataclass(slots=True)
class RespondResult:
    """Combined evaluation + reply from a single LLM call."""
    ai_reply: str              # Marta's conversational response (with recast)
    corrections: list[Correction]  # Grammar errors found in user's message
    is_grammatically_correct: bool
    should_continue: bool      # LLM-decided + hard cap
    hint: str | None           # Scaffolding hint for struggling users (A1 only)
```

The method signature:

```python
def respond_to_user(
    self,
    messages: list[ConversationMessage],
    user_text: str,
    topic: str,
    concept: str,
    difficulty: int = 1,
) -> RespondResult:
```

Use gpt-4o-mini (NOT gpt-4o) with OpenAI's `response_format` parameter
for structured JSON output. The schema should match RespondResult.

### 3. The system prompt (this is the critical part)

The system prompt for respond_to_user should be structured in sections:

```
{MARTA_PERSONA}

CURRENT CONVERSATION CONTEXT:
- Learner level: {cefr_level}
- Grammar target: {concept_name}
- Topic: {topic}
- Conversation turn: {turn_number} of ~4

YOUR TASK:
Read the learner's last message and do THREE things simultaneously:

1. EVALUATE: Check their Spanish for grammar errors, focusing on
   {concept_name}. Only flag errors in the TARGET grammar — if they
   make a different kind of mistake that doesn't affect comprehension,
   let it go. This is focused practice, not a red-pen review.

2. REPLY: Write your conversational response as Marta. 1-2 sentences
   in Spanish. If they made errors in the target grammar, naturally
   RECAST the correct form in your reply WITHOUT pointing it out.

   RECAST EXAMPLE:
   Target: preterite tense
   User says: "Ayer yo como pizza"
   BAD reply: "Se dice 'comí', no 'como'. ¿Qué tipo de pizza?"
   GOOD reply: "¡Ah, comiste pizza! Yo también comí pizza ayer, de
   champiñones. ¿Qué tipo pediste?"
   (Notice: the correct "comiste/comí" appears naturally, plus a
   follow-up question that requires preterite again)

3. STEER: Your reply should include a follow-up question that
   requires the learner to use {concept_name} again. Keep practicing
   the same grammar structure through natural conversation.

{SCAFFOLDING_RULES}

{CONCEPT_STEERING_HINT}

RESPONSE FORMAT:
Return a JSON object with:
- "reply": your response as Marta (1-2 sentences, Spanish only)
- "corrections": array of objects with "original", "corrected",
  "explanation" (1 sentence), "concept_id" — ONLY for target grammar
  errors. Empty array if their grammar was correct.
- "is_correct": boolean — was the target grammar used correctly?
- "should_continue": boolean — true unless the conversation has reached
  a natural goodbye, the topic is exhausted, or you sense the learner
  wants to stop. Always true for turns 1-2.
- "hint": string or null — ONLY at difficulty 1, if the learner seems
  stuck (very short response, question marks, English words). Provide
  a partial sentence they can complete. Example:
  "💡 Intenta: Ayer yo _____ (ir = to go) al..."
  At difficulty 2-3, always null.
```

### 4. Scaffolding rules (injected into system prompt based on difficulty)

```python
SCAFFOLDING_RULES = {
    1: """
SCAFFOLDING (A1 - Maximum support):
- If the learner seems stuck (short response, English words, "???"),
  provide a hint with a partial sentence structure
- Use simple, high-frequency vocabulary only
- It's okay to include a brief English translation in parentheses
  for one key word per response
- Keep your sentences SHORT (under 10 words each)
- Ask yes/no or either/or questions to reduce cognitive load
  Example: "¿Comiste pizza O pasta?" instead of "¿Qué comiste?"
""",
    2: """
SCAFFOLDING (A1-A2 - Moderate support):
- Only help if the learner explicitly asks or seems confused
- No English translations
- Use vocabulary appropriate for upper-beginner
- Ask open-ended questions but keep them focused
  Example: "¿Qué hiciste?" not "Cuéntame todo sobre tu fin de semana"
""",
    3: """
SCAFFOLDING (A2 - Minimal support):
- No hints, no English, no simplification
- Use natural vocabulary and sentence structures
- Challenge with slightly more complex follow-ups
- Ask questions that require extended responses
  Example: "¿Qué fue lo más interesante de tu viaje?"
""",
}
```

### 5. Concept steering hints (injected into system prompt based on concept)

Create a dictionary mapping concept categories to specific steering instructions:

```python
CONCEPT_STEERING = {
    "preterite": "Ask about completed past actions: what they did, where they went, what happened. Questions like '¿Qué hiciste...?' or '¿Adónde fuiste...?'",
    "present-tense": "Ask about daily routines, habits, current states. Questions like '¿Qué haces normalmente...?' or '¿Cómo es tu día típico?'",
    "ser-estar": "Ask questions that require describing states (estar) vs identity/characteristics (ser). Mix both: '¿Cómo es tu ciudad?' and '¿Cómo estás hoy?'",
    "gustar": "Ask about preferences, likes/dislikes. '¿Qué tipo de música te gusta?' or '¿Te gustan los deportes?'",
    "subjunctive": "Create scenarios requiring wishes, recommendations, or doubts. '¿Qué le recomiendas a tu amigo?' or 'Espero que...'",
    "imperative": "Create scenarios requiring commands or instructions. '¿Cómo se prepara tu comida favorita?' (recipe = commands)",
    "future": "Ask about plans, predictions, intentions. '¿Qué vas a hacer este fin de semana?' or '¿Cómo crees que será el futuro?'",
    "reflexive": "Ask about daily routines involving reflexive verbs. '¿A qué hora te levantas?' or '¿Cómo te preparas por la mañana?'",
}

# Fallback: look for partial matches in concept_id
def get_concept_steering(concept_id: str) -> str:
    for key, hint in CONCEPT_STEERING.items():
        if key in concept_id.lower():
            return hint
    return "Ask follow-up questions that naturally require the target grammar structure in the response."
```

### 6. Update the opener to use concept steering

The generate_opener method should include the steering hint so the
FIRST question already forces the target grammar:

```
"Generate a conversation opener as Marta. 1-2 sentences in Spanish.
The opener MUST ask a question that REQUIRES the learner to respond
using {concept_name}.

{concept_steering_hint}

Topic: {topic}
Difficulty: {cefr_level}

Example for preterite + food topic:
'¡Oye! Ayer descubrí un restaurante increíble cerca de mi universidad.
¿Tú qué comiste ayer?'"
```

### 7. Update flow_routes.py to use respond_to_user

In the `conversation_respond` route, replace the two-step flow:

OLD:
```python
evaluation = engine.evaluate_response(user_message, concept_id, difficulty)
ai_reply = engine.generate_reply(messages, topic, concept_id, difficulty)
```

NEW:
```python
result = engine.respond_to_user(
    messages=messages,
    user_text=user_message,
    topic=topic,
    concept=concept_id,
    difficulty=difficulty,
)
# result.ai_reply is the conversational response WITH recast
# result.corrections has the grammar errors for the summary
# result.should_continue decides if conversation keeps going
# result.hint is scaffolding for A1 learners
```

Use result.should_continue AND the hard cap (user_turn_count >= max_turns)
to decide when to end. The LLM can end early if the conversation reaches
a natural goodbye, but the hard cap prevents infinite conversations.

### 8. Update the template for hints

In templates/partials/flow_conversation.html, add a hint area below
the input field:

```html
{% if hint %}
<div id="scaffolding-hint" class="mt-2 px-4 py-2 bg-violet-500/10
     rounded-lg text-sm text-violet-300 italic">
  {{ hint }}
</div>
<script>
  // Hide hint when user starts typing
  document.querySelector('input[name="user_message"]')
    .addEventListener('focus', function() {
      var hint = document.getElementById('scaffolding-hint');
      if (hint) hint.style.opacity = '0.3';
    });
</script>
{% endif %}
```

### 9. Deprecate old methods

Mark evaluate_response and generate_reply as deprecated with a comment
pointing to respond_to_user. Keep them for now in case other code
references them, but the flow_routes.py should only use respond_to_user.

### 10. Testing

Write tests in tests/test_conversation_v2.py:

- Mock the OpenAI client to return structured JSON
- Test that respond_to_user returns all required fields
- Test that hints are generated at difficulty 1 when user sends short/confused response
- Test that hints are NULL at difficulty 3
- Test that should_continue is true for turns 1-2
- Test that corrections only contain target grammar errors (not all errors)
- Test that the concept steering hint is included in the prompt for known concepts
- Test the fallback when OpenAI is unavailable (should return a generic
  reply + empty corrections)
- Test that the opener includes concept-forcing questions

### Notes

- Use gpt-4o-mini for EVERYTHING. The current evaluate_response uses
  gpt-4o which is 25x more expensive. Mini is good enough for grammar
  checking — it's pattern matching, not deep reasoning.
- The persona (Marta) should feel consistent across turns. Include her
  name in the system prompt so she can occasionally reference herself.
- The JSON structured output should use OpenAI's response_format with
  strict schema. If you can't use structured outputs (API version issue),
  fall back to regular JSON mode with a clear schema in the prompt.
- Keep the _fallback methods for when AI is unavailable — they should
  still work without an API key.
