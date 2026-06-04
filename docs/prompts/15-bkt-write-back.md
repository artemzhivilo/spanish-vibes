# Prompt 15: Activity Results → BKT Write-Back

```
Currently, tutor activities evaluate the learner's performance but the
results only feed into the planner's narrative context (via grammar_notes
markdown). The BKT mastery scores in the concept_knowledge table never
get updated from tutor activities. This means the curriculum system
(concept graph, tier unlock, progress tracking) stays frozen.

Bridge the gap: when a tutor activity completes, write the results back
to BKT.

### 1. Create a write-back helper in tutor_tools.py (or a new file)

```python
def write_activity_results_to_bkt(
    concept_id: str | None,
    attempts: list[dict],  # [{correct: bool, concept_id: str}, ...]
) -> None:
    """Update BKT mastery scores based on activity results.

    Called after each tutor activity completes. Maps activity outcomes
    to concept_knowledge updates.

    Args:
        concept_id: Primary concept targeted (from planner params).
            May be None if the activity was freeform.
        attempts: List of individual attempt outcomes. Each has:
            - correct: bool — did they get this attempt right?
            - concept_id: str — which concept this attempt maps to
              (may differ from the primary concept_id if the activity
              tested multiple things)
    """
```

Implementation:
- Import get_concept_knowledge and update_concept_knowledge from flow_db
- Import bkt_update from bkt
- For each attempt:
  - Look up current p_mastery for the concept
  - Run bkt_update(p_mastery, is_correct)
  - Call update_concept_knowledge with the new p_mastery

### 2. Map activity results to BKT attempts

Each activity type produces different kinds of results. Map them:

**Translation challenge:**
- Each sentence is one attempt
- concept_id = the target_grammar from planner params
- correct = communicated_successfully from the evaluator
  (communication success, not grammar perfection)

**Conjugation drill:**
- Each drill item is one attempt
- concept_id = map verb+tense to a concept_id from concepts.yaml
  (e.g., "tener" + "preterite" → "preterite_irregular")
  Create a simple mapping function for this
- correct = exact match (already evaluated locally)

**Conversation:**
- Trickier. The conversation evaluator (if it exists) returns
  corrections and grammar observations, not per-attempt scores.
- For now: if the planner's result_summary mentions grammar wins/losses,
  extract them. OR: skip BKT write-back for conversations and rely on
  the planner's grammar_notes updates instead.
- This is fine — conversations are where the planner's qualitative
  assessment matters most. BKT is better suited for discrete items.

**Circumlocution challenge:**
- communication_score > 0.5 = correct attempt on the target concept
- One attempt per challenge

### 3. Wire into the activity completion handlers

In tutor_routes.py (or tutor_tools.py, wherever activity completion is
handled):

After translation challenge completes:
```python
attempts = [
    {"correct": result["communicated_successfully"], "concept_id": target_grammar}
    for result in sentence_results
]
write_activity_results_to_bkt(target_grammar, attempts)
```

After conjugation drill completes:
```python
attempts = [
    {"correct": item["correct"], "concept_id": map_verb_to_concept(item["verb"], item["tense"])}
    for item in drill_results
]
write_activity_results_to_bkt(primary_concept, attempts)
```

### 4. Concept ID mapping

The planner uses freeform concept names like "preterite_irregular" or
"present_tense" in its tool calls. These need to map to concept IDs from
concepts.yaml. Create a simple mapping function:

```python
def map_grammar_to_concept_id(grammar_label: str) -> str | None:
    """Best-effort mapping from planner's grammar label to concept_id.

    Returns None if no match found (skip BKT update in that case).
    """
```

Use fuzzy matching or a simple lookup dict. The concepts in concepts.yaml
have IDs like "greetings", "present_tense_regular", "preterite_irregular",
etc. The planner's labels will be similar but not always exact matches.

### 5. Safety: don't break existing flow BKT

The existing flow system (flow_routes.py, evaluation.py) already updates
concept_knowledge through its own paths. Make sure the tutor write-back
doesn't conflict — both systems use the same table and the same BKT math,
so they should compose cleanly. Just be careful not to double-count.

Test: complete a tutor session with a translation challenge, then check
the concept_knowledge table to verify mastery scores were updated.
```
