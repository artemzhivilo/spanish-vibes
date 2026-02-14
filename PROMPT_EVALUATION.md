# Post-Conversation Evaluation — Implementation Prompt

## Context

Read `PROMPT.md` for full project context, `DESIGN_IDEAS.md` sections "Technical Architecture" (post-conversation evaluation flow diagram) and "Adaptive Placement & Multi-Dimensional Profiling" (conversation as diagnostic). Read `BACKLOG.md` Step 3.

**The goal:** After every conversation ends, make a single LLM call that extracts structured intelligence from the conversation. This is the architectural hub — it feeds concept mastery (BKT), vocabulary tracking, user facts (for future memory system), and engagement quality signals. Right now the summary is purely mechanical (count corrections, compute score). This replaces that with something much richer.

**Dependency:** Assumes the persona system (Steps 1+2) is already implemented. `conversation.py` accepts persona objects, `persona_id` is stored in `flow_conversations`.

## What to build

### 1. New `evaluation.py` module

Create `src/spanish_vibes/evaluation.py` — a single module with one main function:

```python
def evaluate_conversation(
    messages: list[ConversationMessage],
    concept_id: str,
    topic: str,
    difficulty: int,
    persona_id: str,
) -> ConversationEvaluation:
```

**What the LLM call should extract (structured JSON):**

```json
{
  "concepts_demonstrated": [
    {
      "concept_id": "preterite_regular",
      "usage_count": 3,
      "correct_count": 2,
      "errors": ["used 'como' instead of 'comí'"]
    },
    {
      "concept_id": "ser_estar",
      "usage_count": 1,
      "correct_count": 1,
      "errors": []
    }
  ],
  "vocabulary_used": ["cocina", "preparar", "delicioso", "receta", "ingredientes"],
  "user_facts": [
    "User has a dog named Max",
    "User likes Italian food",
    "User lives in Melbourne"
  ],
  "persona_observations": [
    "User seemed enthusiastic about cooking topic",
    "User struggled with preterite irregular verbs"
  ],
  "engagement_quality": 0.75,
  "estimated_cefr": {
    "vocabulary": "A2",
    "grammar": "A1",
    "fluency": "A2",
    "comprehension": "B1"
  },
  "summary_for_user": "You practiced preterite tense well! You used 'comí' and 'fui' correctly. Watch out for irregular forms — 'como' should be 'comí' when talking about the past."
}
```

**System prompt for the evaluation call:**

The LLM gets the full conversation transcript + context about what concept was being practiced. It should:
- Identify ALL grammar concepts the user demonstrated (not just the target one) — scan for verb tenses, ser/estar, gender agreement, etc.
- List all meaningful Spanish vocabulary the user produced (same filtering as `_extract_spanish_words` in `words.py` — no stop words)
- Extract personal facts the user revealed (these become future `user_profile` entries)
- Note observations about the user for the specific persona (these become future `persona_memories`)
- Rate engagement quality 0.0-1.0 (based on message length, complexity, enthusiasm, willingness to try)
- Estimate CEFR levels across dimensions

Use `gpt-4o-mini` for cost efficiency — this doesn't need the big model. Temperature 0.3 for consistency.

### 2. `ConversationEvaluation` dataclass

Add to `evaluation.py` (or `models.py` if preferred):

```python
@dataclass
class ConceptEvidence:
    concept_id: str
    usage_count: int
    correct_count: int
    errors: list[str]

@dataclass
class ConversationEvaluation:
    concepts_demonstrated: list[ConceptEvidence]
    vocabulary_used: list[str]
    user_facts: list[str]
    persona_observations: list[str]
    engagement_quality: float  # 0.0-1.0
    estimated_cefr: dict[str, str]  # {"vocabulary": "A2", "grammar": "A1", ...}
    summary_for_user: str  # Human-readable feedback
```

### 3. Wire evaluation into the conversation summary flow

In `flow_routes.py` `conversation_summary` endpoint:

**After** the existing `generate_summary()` call and `harvest_conversation_words()`, add:

```python
from .evaluation import evaluate_conversation

evaluation = evaluate_conversation(
    messages=messages,
    concept_id=concept_id,
    topic=topic,
    difficulty=difficulty,
    persona_id=row["persona_id"] or "marta",
)
```

Then use the evaluation results:

**a) Update BKT for demonstrated concepts:**
```python
from .bkt import bkt_update
from .flow_db import update_concept_knowledge, get_concept_knowledge

for evidence in evaluation.concepts_demonstrated:
    # Production evidence from conversation — apply with boosted weight
    # Each correct usage counts as a successful attempt
    ck = get_concept_knowledge(evidence.concept_id)
    if ck:
        for _ in range(evidence.correct_count):
            new_p = bkt_update(ck.p_mastery, correct=True)
            update_concept_knowledge(evidence.concept_id, new_p, is_correct=True)
        for _ in range(evidence.usage_count - evidence.correct_count):
            new_p = bkt_update(ck.p_mastery, correct=False)
            update_concept_knowledge(evidence.concept_id, new_p, is_correct=False)
```

This is a big deal — currently conversations DON'T update BKT at all. Only MCQ responses do. This means conversation practice finally feeds back into the mastery system.

**b) Track vocabulary:**
The `harvest_conversation_words()` call already handles this, but the evaluation gives us a cleaner word list. Could use `evaluation.vocabulary_used` instead of or in addition to the raw extraction. Either approach works — the raw extraction is already wired in, so the evaluation vocabulary is a nice validation/supplement.

**c) Store user_facts and persona_observations:**
For now, just log them. The memory system (Step 4) will add the tables to persist these. Don't build the tables yet — just make sure the data is available.

```python
# TODO: Step 4 will persist these
# For now, log for debugging
if evaluation.user_facts:
    print(f"[eval] User facts discovered: {evaluation.user_facts}")
if evaluation.persona_observations:
    print(f"[eval] Persona observations: {evaluation.persona_observations}")
```

**d) Use `summary_for_user` in the UI:**
Pass `evaluation.summary_for_user` to the conversation summary template as an additional field. Display it as a "feedback" section above or below the corrections.

### 4. Update the summary template

In `templates/partials/flow_conversation_summary.html`:

Add an evaluation feedback section. Something like:

```html
{% if evaluation_summary %}
<div class="rounded-xl bg-emerald-500/10 ring-1 ring-emerald-500/20 p-4 mb-4">
  <p class="text-xs font-bold uppercase tracking-wide text-emerald-400 mb-2">Feedback</p>
  <p class="text-sm text-slate-200 leading-relaxed">{{ evaluation_summary }}</p>
</div>
{% endif %}
```

Also show concepts practiced (from the evaluation, not just the target concept):

```html
{% if concepts_practiced and concepts_practiced|length > 1 %}
<p class="text-xs text-slate-400 mt-2">
  Concepts practiced: {{ concepts_practiced | join(', ') }}
</p>
{% endif %}
```

### 5. Graceful fallback

The evaluation LLM call might fail (rate limits, timeout, etc.). Wrap it in try/except and fall back to the existing mechanical summary if it fails. The conversation should never get stuck because evaluation failed.

```python
try:
    evaluation = evaluate_conversation(...)
    # Use evaluation results
except Exception as exc:
    print(f"[eval] Evaluation failed, using mechanical summary: {exc}")
    evaluation = None
```

## What NOT to build yet

- No `persona_memories` table (Step 4)
- No `user_profile` table (Step 4)
- No `persona_engagement` table (Step 5)
- No enjoyment scoring computation (Step 5)
- Don't change the existing `generate_summary()` method — keep it as the fallback. The evaluation augments it, doesn't replace it.

## Key design decisions

- **Use gpt-4o-mini** for the evaluation call — it's a structured extraction task, doesn't need the big model
- **Production > recognition** — correct usage of a concept in conversation should update BKT more aggressively than an MCQ correct answer. The code above does this by applying one BKT update per usage instance.
- **Fail gracefully** — evaluation is additive. If the LLM call fails, the conversation still works exactly as before.
- **Log user_facts and persona_observations** — don't persist to DB yet, but make sure the extraction pipeline works so Step 4 just needs to add the storage.

## Files to create

1. `src/spanish_vibes/evaluation.py` — New module with `evaluate_conversation()` and dataclasses

## Files to modify

1. `src/spanish_vibes/flow_routes.py` — Wire evaluation into `conversation_summary` endpoint, pass results to template
2. `templates/partials/flow_conversation_summary.html` — Add evaluation feedback section
3. `src/spanish_vibes/conversation.py` — Only if needed to expose more data to the evaluation (probably not)

## Testing

- Verify evaluation returns valid structured data for a sample conversation
- Verify BKT updates happen for demonstrated concepts
- Verify fallback works when evaluation LLM call fails
- Verify summary template renders evaluation feedback
- Verify existing conversation flow still works end-to-end
