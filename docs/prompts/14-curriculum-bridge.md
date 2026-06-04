# Prompt 14: Curriculum Bridge — Concept Graph + BKT into Planner Context

```
The tutor planner currently reads three markdown files for context:
learner_profile.md, session_journal.md, grammar_notes.md. But it has
ZERO connection to the existing curriculum system: 61 concepts in a DAG
(data/concepts.yaml), BKT mastery tracking (concept_knowledge table),
prerequisite chains, and difficulty tiers.

Bridge the gap by adding a CURRICULUM STATUS section to the planner context.

### 1. Add build_curriculum_context() to tutor_memory.py

```python
def build_curriculum_context(user_id: str) -> str:
    """Build a curriculum status summary from the concept graph + BKT data.

    Returns a markdown string showing:
    - Current tier and progress within it
    - Concepts in progress (with mastery %)
    - Next recommended concepts (prerequisites met)
    - Concepts being avoided (many attempts, low mastery)
    """
```

Implementation:
- Import load_concepts from concepts.py and get_all_concept_knowledge
  from flow_db.py
- Group concepts by difficulty_level (tier)
- For each concept, look up its BKT state (p_mastery, n_attempts)
- Build a compact summary like:

```
## CURRICULUM STATUS

Current tier: 2 (Basic Grammar) — 60% complete
Tier 1 (Foundations): 5/5 mastered ✅
Tier 2 (Basic Grammar): 3/5 mastered, 2 in progress
  🔄 articles_definite — 0.65 mastery (8 attempts, struggling with el/la agreement)
  🔄 present_tense_regular — 0.72 mastery (12 attempts)
  ✅ greetings — mastered
  ✅ numbers_1_20 — mastered
  ✅ colors_basic — mastered

Next available: adjective_agreement (prerequisites met), present_tense_irregular

Avoidance alert: articles_definite has 8 attempts but only 0.65 mastery — may need focused drill
```

Keep it compact — aim for ~300-500 tokens. The planner doesn't need to see
mastered concepts in detail, just the counts. Focus the detail on:
- Concepts currently in progress (0.3 < p_mastery < 0.9)
- Concepts that might be stuck (many attempts, low mastery)
- Next unlock candidates

### 2. Update build_planner_context() to include curriculum status

In tutor_memory.py, update build_planner_context() to call
build_curriculum_context() and append it as a fourth section:

```python
def build_planner_context(user_id: str) -> str:
    profile = read_learner_profile(user_id)
    journal = read_session_journal(user_id, last_n=5)
    grammar = read_grammar_notes(user_id)
    curriculum = build_curriculum_context(user_id)

    return (
        f"## LEARNER PROFILE\n\n{profile}"
        f"\n\n---\n\n## RECENT SESSIONS (last 5)\n\n{journal}"
        f"\n\n---\n\n## GRAMMAR STATUS\n\n{grammar}"
        f"\n\n---\n\n## CURRICULUM STATUS\n\n{curriculum}"
    )
```

### 3. Update the planner system prompt in tutor_agent.py

Add guidance for using the curriculum status section. After the existing
PEDAGOGICAL PRINCIPLES section, add:

```
CURRICULUM AWARENESS:
- The CURRICULUM STATUS section shows mastery data from the concept graph.
- Use it to pick the RIGHT concept to target — don't guess, check the data.
- If a concept shows many attempts but low mastery, it needs focused work
  (drill → teach → retry, not just more conversation).
- If a concept shows high mastery in drills but the grammar_notes say it
  fails in free speech, prioritize transfer practice (conversation).
- When choosing what to work on, prefer concepts that are:
  1. Currently in progress (some attempts, not yet mastered)
  2. Available (prerequisites met) but not started
  3. Stuck (many attempts, low mastery) — these need a different approach
- Don't introduce concepts whose prerequisites aren't met.
- The curriculum data gives you NUMBERS. The grammar_notes give you CONTEXT.
  Use both: the numbers tell you WHAT to work on, the notes tell you HOW.
```

### 4. Handle the "no concept_knowledge rows" case

For brand new users who haven't done any flow activities, the
concept_knowledge table may have no rows or only default rows
(p_mastery=0.0, n_attempts=0). The build_curriculum_context() function
should handle this gracefully:
- If no rows exist, return a simple message: "New learner — no curriculum
  data yet. Start with Tier 1 basics."
- If rows exist but all are at 0.0, same thing.

### 5. Don't import from tutor_memory into flow code

The curriculum bridge reads FROM the flow system (concepts.py, flow_db.py)
INTO the tutor system (tutor_memory.py). The flow system should NOT import
from tutor code. This is a one-way dependency.

Test: start a tutor session and check the planner's context (look at the
planner_decisions log in the DB) to verify the CURRICULUM STATUS section
appears and contains real data.
```
