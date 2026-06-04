# Spanish Vibes — Agent-Based Tutor Architecture

## The Core Idea

Replace the current deterministic flow engine (`flow.py` → pick concept → pick card type → render)
with an **AI agent loop** where a smart model decides what to do next and has a toolkit of
interactive UI activities it can deploy.

The app becomes a thin rendering layer. The intelligence lives in the agent.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                    BROWSER (HTMX)                    │
│                                                      │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐            │
│  │  Chat UI  │ │ MCQ Card │ │Image Desc│  ... more  │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘            │
│       │             │            │                    │
│       └─────────────┼────────────┘                   │
│                     │  user interaction               │
│                     ▼  (HTMX POST)                   │
├─────────────────────────────────────────────────────┤
│                 FASTAPI SERVER                        │
│                                                      │
│  ┌─────────────────────────────────────────────┐    │
│  │              AGENT LOOP                      │    │
│  │                                              │    │
│  │  1. Receive user action + session context    │    │
│  │  2. Call PLANNER model (smart, slow)         │    │
│  │  3. Planner returns tool call(s)             │    │
│  │  4. Execute tool → render HTMX partial       │    │
│  │  5. Stream partial to browser                │    │
│  │  6. Wait for next user action                │    │
│  │                                              │    │
│  │  Tools available to the agent:               │    │
│  │  ┌────────────────────────────────────┐      │    │
│  │  │ start_conversation(...)            │      │    │
│  │  │ show_mcq(...)                      │      │    │
│  │  │ show_image_description(...)        │      │    │
│  │  │ show_conjugation_drill(...)        │      │    │
│  │  │ show_translation_challenge(...)    │      │    │
│  │  │ show_whatsapp_task(...)            │      │    │
│  │  │ show_teach_card(...)               │      │    │
│  │  │ give_feedback(...)                 │      │    │
│  │  │ update_learner_state(...)          │      │    │
│  │  │ end_session(...)                   │      │    │
│  │  └────────────────────────────────────┘      │    │
│  └─────────────────────────────────────────────┘    │
│                                                      │
│  ┌──────────────────────┐  ┌────────────────────┐   │
│  │   WORKER MODELS      │  │   EXISTING CODE    │   │
│  │   (fast, cheap)      │  │                    │   │
│  │                      │  │  conversation.py   │   │
│  │  - MCQ generation    │  │  evaluation.py     │   │
│  │  - Grammar check     │  │  bkt.py            │   │
│  │  - Translation       │  │  personas.py       │   │
│  │  - Content gen       │  │  memory.py         │   │
│  │                      │  │  interest.py       │   │
│  └──────────────────────┘  └────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

---

## The Two-Tier LLM Strategy

This is where the speed/intelligence balance lives. Not everything needs a
genius model. We chain calls strategically.

### Tier 1: The Planner (Smart, Slow)

**Model:** `gpt-5.2` (OpenAI flagship)
**When it runs:** Once per "decision point" — when the agent needs to decide
what to do next (session start, after user completes an activity, after N turns
of conversation, when user seems stuck).

**What it sees:**
- Learner profile (level, weak spots, interests, recent performance)
- Session history (what activities were done, how they went)
- Available tools (what UI activities it can deploy)
- Pedagogical guidelines (DELE A2 prep strategy)

**What it decides:**
- Which tool to call next (conversation? drill? image task?)
- Parameters for that tool (which concept to target, difficulty, persona, scenario)
- Whether to escalate/de-escalate difficulty
- Whether to switch activity types (learner seems bored/frustrated)

**Cost control:** The planner runs infrequently — maybe 5-10 calls per session.
It's like a chess player thinking about the next move, not a machine reacting
to every keystroke.

### Tier 2: Workers (Fast, Cheap)

**Model:** `gpt-5.2-mini` (conversation, evaluation, content gen) / `gpt-5.2-nano` (classification, simple grammar checks)
**When they run:** During activities — generating MCQs, evaluating grammar,
generating conversation responses, creating image descriptions, translating.

**These are the existing calls you already have**, just wrapped as tool
implementations. `conversation.py`'s `respond_to_user()` is already a
Tier 2 worker. `flow_ai.py`'s `generate_mcq_batch()` is another.

### Tier 1→2 Context Handoff: The Worker Briefing

This is what makes cheap models punch above their weight. When the planner
calls a tool, it doesn't just pass parameters — it attaches a **worker
briefing** that gives the Tier 2 model rich context about the learner and
the current pedagogical intent.

**Without briefing** (what we have now):
```
System: You are Marta... CONCEPT STEERING: Ask about completed past actions.
```
The worker knows the concept but not the learner's specific struggles.

**With briefing** (what the planner provides):
```
System: You are Marta... CONCEPT STEERING: Ask about completed past actions.

WORKER BRIEFING (from tutor planner):
- This learner keeps saying "teno" instead of "tuve" — they've gotten it
  wrong 3 times today (twice in conversation, once in a drill)
- They just practiced the correct form in a conjugation drill and got it
  right. This conversation is the "transfer test" — can they use it in
  free speech?
- ir→fui and hacer→hice are solid now, don't over-drill those
- The learner responds well to humor and music topics
- If they get tuve right, react with genuine excitement — this is a
  breakthrough moment
- Be slightly more aggressive with recasting tener forms: use tuve/tuvo/
  tuvieron in your own replies so they hear it repeatedly
- Communication style preference: the learner likes to try complex ideas
  with simple vocab — encourage this, don't simplify your questions
```

The briefing is generated by the planner (Tier 1) and injected as a
`{worker_briefing}` template variable into the worker's system prompt.
The worker doesn't need to be smart enough to figure out the pedagogy —
the planner already did that. The worker just needs to follow the briefing.

**Cost:** Nearly zero. It's ~200 extra tokens in the worker's context window.
On GPT-4o-mini that's fractions of a cent. The expensive planner call already
happened — you're just passing its intelligence downstream.

**Implementation:** Every tool call includes a `worker_briefing: str` field.
The prompt templates get a new `{worker_briefing}` variable. If the briefing
is empty (legacy/fallback), the worker behaves exactly as before.

```python
@dataclass
class WorkerBriefing:
    """Context passed from planner to worker for a specific activity."""
    learner_weaknesses: list[str]     # specific errors to watch for
    session_narrative: str            # what happened so far today
    pedagogical_intent: str           # why this activity was chosen
    correction_aggressiveness: str    # "gentle" / "moderate" / "firm"
    tone_notes: str                   # personality/style guidance
    success_criteria: str             # what "good" looks like for this activity

    def to_prompt_block(self) -> str:
        """Format as a prompt section for injection into worker system prompt."""
        ...
```

### The Chain in Practice

```
SESSION START
  │
  ▼
PLANNER (smart): "Learner needs preterite drilling. They like music.
                  Start with a conversation about a concert they went to."
  │
  ▼
Tool: start_conversation(persona="marta", topic="conciertos",
                         concept="preterite", difficulty=2)
  │
  ▼
WORKER (fast): generate_opener() → "¡Oye! Ayer fui a ver a Rosalía..."
  │
  ▼
[User chats for 4 turns — each turn is a WORKER call via respond_to_user()]
  │
  ▼
WORKER (fast): evaluate_conversation() → corrections, score
  │
  ▼
PLANNER (smart): "They got 2/4 preterite forms right. Irregular verbs
                  are the issue (ir → fui, hacer → hice). Switch to a
                  quick conjugation drill targeting irregulars, then do
                  a WhatsApp task to see if they can apply it."
  │
  ▼
Tool: show_conjugation_drill(verbs=["ir","hacer","tener"],
                             tense="preterite", count=6)
  │
  ▼
WORKER (fast): generate drill items, evaluate answers
  │
  ▼
PLANNER (smart): "They nailed ir/hacer but still mixing up tener/tuvo.
                  Do an image description task about a trip (forces
                  past tense narrative)."
  │
  ▼
Tool: show_image_description(scene="vacation_beach",
                             tense_focus="preterite",
                             target_verbs=["tener","ir","hacer"])
  │
  ... and so on
```

---

## Tool Definitions

Each tool corresponds to a UI activity. The planner calls them by name with
parameters. The server executes the tool, renders an HTMX partial, and streams
it to the browser.

**Every tool accepts a `worker_briefing` field** — rich context from the planner
that gets injected into the Tier 2 worker's system prompt. This is what makes
cheap models perform like expensive ones. See "Tier 1→2 Context Handoff" above.

### Tool 1: `start_conversation`

**What it does:** Opens the existing conversation chat interface.
**Reuses:** `ConversationEngine`, persona system, clickable word translations.
**Parameters:**
```json
{
  "persona": "marta",
  "topic": "what you did last weekend",
  "concept": "preterite",
  "difficulty": 2,
  "max_turns": 4,
  "conversation_type": "general_chat",
  "scenario": null,
  "guardrails": "Focus on irregular preterite: ir, hacer, tener",
  "worker_briefing": "Learner keeps saying 'teno' instead of 'tuve'. They just got it right in a drill — this conversation is the transfer test. If they get tuve right, react with excitement. Use tuve/tuvo in your own replies so they hear it repeatedly. They like music and humor."
}
```
**Visual format:**
```
┌─────────────────────────────────────────────────┐
│  💬 Marta                                        │
│                                                   │
│  "¡Oye! ¿Qué tal el finde? Yo fui a ver a       │
│   Rosalía el sábado. ¡Fue increíble!"            │
│                                                   │
│  ┌─────────────────────────────────────────┐     │
│  │  [Your message...]              [Send]  │     │
│  └─────────────────────────────────────────┘     │
│                                                   │
│  Turn 1 of 4                   💡 Tap any word   │
└─────────────────────────────────────────────────┘
```
Conversation messages stack vertically. Persona messages left-aligned with avatar,
learner messages right-aligned. Clickable words show translation popover on tap.
Turn counter shows progress but doesn't feel like a countdown.

**Completed state:** Card collapses to a one-line summary:
`💬 Conversation with Marta — preterite practice (3/4 correct)`

**Returns to planner:** Conversation summary (corrections, concepts demonstrated,
score, engagement quality). On early exit via distress signal, includes the signal
details and partial results.

### Tool 2: `show_mcq`

**What it does:** Shows a multiple-choice question card.
**Reuses:** MCQ cache, `flow_ai.py` generation.
**Parameters:**
```json
{
  "concept": "preterite_irregular",
  "count": 3,
  "difficulty": 2,
  "focus": "ir/hacer/tener conjugations"
}
```
**Returns:** Score (n_correct / n_total), specific errors.

### Tool 3: `show_conjugation_drill`

**What it does:** Rapid-fire verb conjugation practice. Shows a subject + infinitive,
learner types the conjugated form. Immediate feedback.
**NEW UI component.**
**Parameters:**
```json
{
  "verbs": ["ir", "hacer", "tener", "estar"],
  "tense": "preterite",
  "persons": ["yo", "tú", "él/ella"],
  "count": 8,
  "time_pressure": false
}
```

**Visual format:**
```
┌─────────────────────────────────────────────────┐
│  ⚡ Conjugation Drill — Pretérito               │
│                                                   │
│  yo / tener  →  [________]                        │
│                                                   │
│  ✅ tú / ir → fuiste                             │
│  ❌ él / hacer → hació  (hizo)                   │
│                                                   │
│  3 of 8                          ⏱ no time limit  │
└─────────────────────────────────────────────────┘
```
Current item shows the subject pronoun and infinitive. Learner types the conjugated
form and hits Enter. Immediate feedback: green check or red X with the correct form.
Previous items stack above in a scrollable list so the learner sees their progress.

**Completed state:** Card collapses to:
`⚡ Conjugation Drill — 6/8 correct (missed: tener yo, poder él)`

**Returns:** Score, average response time, specific verb/person combos that failed.

### Tool 4: `show_translation_challenge`

**What it does:** Shows an English sentence, learner writes it in Spanish.
AI evaluates grammar + vocabulary.
**NEW UI component.**
**Parameters:**
```json
{
  "sentences": [
    "Yesterday I went to the beach with my friends",
    "She made dinner and we ate together"
  ],
  "target_grammar": "preterite",
  "difficulty": 2,
  "show_hints": false
}
```
**Returns:** Per-sentence evaluation (corrections, score).

### Tool 5: `show_image_description`

**What it does:** Shows an image (generated or stock) and asks the learner to
describe it. DELE A2 Task 2 style.
**NEW UI component.**
**Parameters:**
```json
{
  "scene_description": "A family having dinner at a restaurant",
  "tense_focus": "preterite",
  "prompt": "Describe what happened at this dinner. Use at least 3 sentences.",
  "min_sentences": 3
}
```
**Image generation:** Either pre-made stock images tagged by theme, or AI-generated
placeholder illustrations (simple, not photorealistic — think Duolingo style).
**Returns:** Evaluation of description (grammar, vocabulary, tense consistency).

### Tool 6: `show_whatsapp_task`

**What it does:** Renders a fake WhatsApp-style conversation thread between
fictional characters. Learner reads it and either answers comprehension questions
or writes a reply. DELE A2 Task 1 style.
**NEW UI component.**
**Parameters:**
```json
{
  "scenario": "friends planning a weekend trip",
  "messages": [
    {"sender": "Ana", "text": "¡Hola! ¿Qué hiciste el fin de semana pasado?"},
    {"sender": "Carlos", "text": "Fui al cine con mi hermana. ¿Y tú?"},
    {"sender": "Ana", "text": "Yo me quedé en casa. Estuve enferma 😷"}
  ],
  "task_type": "reply",
  "task_prompt": "Reply to Ana as if you are her friend. Tell her what you did and wish her well.",
  "target_grammar": "preterite"
}
```
**Returns:** Evaluation of reply (grammar, appropriateness, tone).

### Tool 7: `show_teach_card`

**What it does:** The planner writes a natural explanation directly in the chat.
No special UI card, no structured template — just the tutor talking. The planner
has the narrative context to explain exactly what the learner is struggling with,
using examples and language that match the learner's interests and level.

**This tool is reactive as well as proactive.** The planner can call it mid-session
when the learner is struggling (triggered by a distress signal from a conversation or
drill), not just as a planned lesson. Example: learner keeps saying "teno" → planner
fires a teach moment specifically about tener irregular stem before retrying.

**Phase 1 implementation:** The planner simply writes the explanation as a tutor
chat message. This is the fastest path to testing whether the pedagogical flow
works (distress signal → explanation → retry). No extra templates needed.

**Parameters:**
```json
{
  "concept": "preterite_irregular",
  "focus": "tener → tuve/tuvo/tuvieron — the irregular stem change",
  "context": "Learner keeps defaulting to 'teno'. Has gotten it right in drills but not in free speech.",
  "explanation": "Hey, let's pause for a sec. So tener is sneaky in the past tense — the stem completely changes. Instead of ten-, it becomes tuv-. So: yo tuve, tú tuviste, él tuvo. Think of it like ten- gets kicked out and tuv- takes over, but the endings stay normal (-e, -iste, -o). Same thing happens with poder → pud- and estar → estuv-. Try saying 'yo tuve' a couple times — tuve, tuve, tuve. Got it? Let's try using it."
}
```

The `explanation` field IS the tutor message. It renders as a normal chat bubble
from the tutor — warm, conversational, targeted. The planner writes it because
only the planner knows:
- What specifically the learner is getting wrong ("teno" not "tuve")
- What they've already been told (don't repeat the same explanation)
- What tone works for this learner (direct, with a touch of humor)
- What examples will land (music/travel references, not abstract grammar)

**Phase 2 enhancement:** Upgrade to a formatted card with conjugation table,
mnemonic, examples — visually scannable and referenceable. The planner would
pass structured params and a Jinja template would render it. But test the
pedagogical flow with plain chat first.

**Returns:** Acknowledged (learner saw it). The planner uses this to know the
learner has been shown the explanation before retrying the concept in an activity.

### Tool 8: `give_feedback`

**What it does:** Shows a feedback/summary card between activities. The planner
uses this to give encouragement, highlight progress, or explain what's coming next.
**NEW UI component (simple).**
**Parameters:**
```json
{
  "message": "Nice work on those irregular verbs! You're getting faster with 'ir' and 'hacer'. Let's try using them in a real conversation now.",
  "show_stats": true,
  "stats": {
    "correct_rate": 0.75,
    "streak": 3,
    "focus_concept": "preterite_irregular"
  }
}
```

### Tool 9: `update_learner_state`

**What it does:** Internal tool — updates BKT mastery, interest scores, memory.
Not visible to learner. The planner calls this after evaluating performance.
**Reuses:** `bkt.py`, `interest.py`, `memory.py`.

### Tool 10: `propose_session_plan`

**What it does:** Generates the opening check-in message. Always the first
tool called in a session. The tutor proposes what to work on, the learner
can agree or redirect.
**Parameters:**
```json
{
  "focus_concepts": ["preterite_irregular"],
  "suggested_flow": ["conversation", "conjugation_drill", "image_description"],
  "session_goal": "Build automatic preterite retrieval for irregular verbs",
  "personalized_note": "Last session: tener→tuve was weak (0/3). ir and hacer were solid.",
  "estimated_duration_min": 20
}
```
**Returns:** Learner's response (agree, redirect, or question).

### Tool 11: `show_circumlocution_challenge`

**What it does:** Gives the learner a complex idea to express using only the
vocabulary they have. Tests communication strategy, not just grammar.
The core DELE A2 skill of "getting your point across."
**NEW UI component.**
**Parameters:**
```json
{
  "prompt_en": "Explain why you changed jobs last year. You were unhappy with your boss and wanted more money.",
  "target_grammar": "preterite",
  "vocabulary_level": "A2",
  "evaluation_focus": "communication_success",
  "hints": ["cambiar = to change", "jefe = boss"]
}
```
**Evaluation criteria:** Did they communicate the idea? Did they use
workarounds creatively? Grammar accuracy is secondary to communication success.
**Returns:** Communication score, grammar score, creative workarounds used.

### Tool 12: `end_session`

**What it does:** Wraps up the session with a summary of what was practiced,
progress made, and suggested next focus areas.

---

## Learner Memory — Narrative Context, Not Database Rows

### The Problem with Parameterized Memory

The current system tracks learning as database numbers:
- `concept_knowledge.p_mastery = 0.45` (what does that *mean*?)
- `interest_topics.score = 0.7` for music (how is that useful to a tutor?)
- `persona_memories` = "Artem likes rock music" (shallow, no pedagogy)

A smart planner model doesn't need floats. It needs *understanding*. The
same way a human tutor keeps notebook pages on each student, not a
spreadsheet of mastery probabilities.

### The Narrative Memory System

The planner maintains a set of markdown files per learner. These are the
primary context source — the planner reads them at session start and
updates them at session end. They're small (2-3K tokens total), rich,
and human-readable.

#### File 1: `learner_profile.md` — Who You Are

Rewritten every ~3-5 sessions as the picture evolves. The planner's
comprehensive understanding of this specific learner.

```markdown
# Learner Profile: Artem
Updated: 2026-02-18

## Level & Stage
Late A2. Solid foundation in present tense, basic preterite regulars.
Ready for B1 grammar structurally, but needs automaticity in A2 forms
before advancing. The bottleneck is retrieval speed, not knowledge.

## Current Focus
Irregular preterite. Specifically:
- tener→tuve/tuvo: Main weakness. Defaults to "teno" under pressure.
  Has gotten it right in isolation (drills) but not yet in free speech.
- poder→pude/pudo: Emerging issue. Avoids using it entirely.
- ir→fui, hacer→hice: Solid as of Feb 15 session. Breakthrough during
  concert conversation with Marta.
- ser→fue vs ir→fue: Not yet tested. Potential confusion point.

## Learning Style
- Prefers conversation over drills, but needs both
- Gets frustrated by repetitive MCQs after ~5 in a row
- Responds very well to humor — Marta's sarcasm works great
- Likes to attempt complex ideas with simple vocab. This is a real
  strength — encourage it rather than simplifying prompts.
- Best sessions are when activities feel connected to real life
  (what he did yesterday, music he listens to, work situations)
- Falls back to English when tired or when vocab gap is too wide
- Energy drops noticeably after ~20 minutes

## Interests & Life Context
These are not just topics — they're pedagogical leverage. The planner
should actively use interests to create scenarios that force target
grammar in contexts the learner actually cares about.

**Music** — Strongest topic by far. Listens to rock, especially
Spanish-speaking artists. Rosalía came up twice, also mentioned Vetusta
Morla. Gets genuinely animated talking about concerts and discovering
new songs. Already proven as preterite material: "fui al concierto",
"escuché una canción nueva" came out naturally. Also good for opinions
(gustar), comparisons, and describing experiences.
→ Use for: preterite, imperfect ("cuando era joven escuchaba..."),
  opinions, circumlocution

**Tech/software** — His actual job. Can discuss work fluently in English
but struggles to describe technical concepts in Spanish. This gap is
itself a learning opportunity — circumlocution practice gold.
→ Use for: circumlocution challenges ("explain your job using simple
  words"), present tense routines ("¿qué haces en tu trabajo?"),
  preterite ("¿qué hiciste hoy en el trabajo?")

**Cooking** — Comes up naturally. Has mentioned making pasta and trying
Spanish recipes. Knows some food vocabulary already.
→ Use for: imperative practice later (recipe = commands), vocabulary
  building, daily routine descriptions

**Travel / Spain** — Has been to Madrid and Barcelona. Wants to go back.
Knows cultural references (La Boquería, El Retiro). Travel memories are
a goldmine for past tense narrative.
→ Use for: preterite ("cuando fui a Madrid..."), imperfect (descriptions
  of places), future (plans to return), image description tasks

**Dead topics — avoid:** Sports (tried twice, conversation died quickly),
fashion, celebrity gossip. Don't waste session time on these.

## DELE A2 Prep
- Exam target: not confirmed, but prep aligns with his goals
- Task exposure: conversation (high), conjugation drill (medium),
  image description (tried once, liked it), WhatsApp task (never),
  circumlocution (never)

## Personality Notes
- Motivated but impatient with plateau feelings
- Appreciates when progress is made visible ("you got tuve right
  3/4 times today vs 0/3 last week")
- Prefers the tutor to lead — doesn't want to choose activities
```

#### File 2: `session_journal.md` — What Happened

Append-only. After each session, the planner writes a brief entry.
Keeps the last ~10 sessions (older entries archived/summarized).

```markdown
# Session Journal

## 2026-02-18 (Session #14)
Focus: Irregular preterite (tener, poder)
Activities: conversation (Marta/music) → conjugation drill → image
description → circumlocution challenge
Duration: 22 min

Key observations:
- tuve clicked in drill (5/6) but reverted to "teno" once in
  conversation. Progress but not yet automatic.
- First time trying image description — wrote 4 sentences, all past
  tense, 3 grammatically correct. He liked this format.
- Circumlocution challenge about changing jobs: communicated the idea
  successfully using simple structures. Said "mi jefe no fue bueno"
  instead of "exigente" — exactly the resourcefulness we want.
- Energy was high for first 15 min, dropped off in last drill.
- poder: avoided entirely. Need to create situations that force it.

Next session plan: Push poder→pude specifically. Try WhatsApp task
format. Keep image description in rotation — it works for him.

## 2026-02-15 (Session #13)
Focus: Irregular preterite (ir, hacer, tener)
Activities: conversation (Marta/concerts) → conjugation drill →
conversation (Diego/weekend)
Duration: 18 min

Key observations:
- BREAKTHROUGH: ir→fui and hacer→hice both used correctly in free
  conversation for the first time. The concert topic was perfect —
  natural context for "fui al concierto" and "hice planes."
- tener still weak. 0/3 in conversation. Needs isolated drilling
  before trying in conversation again.
- Marta persona is working really well. Consider keeping her for
  the next 2-3 sessions to build continuity.
```

#### File 3: `grammar_notes.md` — Linguistic Patterns

More structured than the journal, tracks specific grammar acquisition.
Updated after each session with concrete evidence.

```markdown
# Grammar Tracking

## Preterite — Regular
Status: SOLID
- -ar verbs (hablé, comí): consistent, automatic
- -er/-ir verbs (comí, viví): consistent
- Last error: none in last 5 sessions

## Preterite — Irregular
Status: IN PROGRESS

### ir → fui/fue/fueron
Status: solid (as of Feb 15)
Evidence: Used correctly 6/6 times across 2 conversations
Notes: Breakthrough via concert topic. "Fui al concierto" is now
automatic. "Fue increíble" also solid.

### hacer → hice/hizo/hicieron
Status: solid (as of Feb 15)
Evidence: 4/4 in conversation, 3/3 in drill
Notes: "¿Qué hiciste?" response pattern is automatic now.

### tener → tuve/tuvo/tuvieron
Status: WEAK — primary focus
Evidence: 1/4 in conversation (Feb 18), 5/6 in drill (Feb 18)
Error pattern: defaults to "teno" or "tenió" under pressure
Notes: Can produce correctly in isolation but not in free speech.
The drill→conversation transfer hasn't happened yet. Need more
reps at the transfer boundary.

### poder → pude/pudo/pudieron
Status: AVOIDANCE — secondary focus
Evidence: 0 attempts in last 3 sessions (avoidance strategy)
Notes: Never attempts it. May not be confident in the form at all.
Need to create forced-production scenarios. Maybe a "what could
you do / couldn't do" exercise about a past trip.

## Present Tense
Status: AUTOMATIC
Notes: No issues. Occasionally uses present when past is needed
(tense switching under cognitive load) but the present forms
themselves are solid.

## Imperfect
Status: NOT YET INTRODUCED
Notes: Will become relevant when preterite is more automatic.
The preterite/imperfect distinction is the big A2→B1 hurdle.

## Ser vs Estar
Status: MOSTLY SOLID
Notes: Occasional hesitation with temporary states (estar cansado)
but not a priority right now.
```

### How the Planner Uses These Files

At session start, the planner receives all three files as context
(~2-3K tokens total). This replaces the old `TutorSessionContext`
dataclass — the narrative IS the context.

```
PLANNER SYSTEM PROMPT:
You are an expert Spanish tutor. Here is everything you know about
this learner:

[learner_profile.md contents]

[session_journal.md contents — last 5 entries]

[grammar_notes.md contents]

Based on this, decide what to work on today...
```

### When the Planner Updates Memory

The planner has two internal tools for memory management:

#### Tool: `update_session_journal`
Called at session end. Appends a new entry to `session_journal.md`.
```json
{
  "entry": "## 2026-02-18 (Session #14)\nFocus: Irregular preterite..."
}
```

#### Tool: `update_grammar_notes`
Called when the planner observes a meaningful change in grammar status
(new error pattern, a breakthrough, status change from WEAK to SOLID).
```json
{
  "concept": "preterite_irregular_tener",
  "update": "Evidence: 5/6 in drill, 1/4 in conversation. Still defaults to 'teno' in free speech."
}
```

#### Tool: `rewrite_learner_profile`
Called every ~3-5 sessions, or when the planner detects the profile is
stale (e.g., learner has progressed beyond what the profile describes).
Full rewrite of `learner_profile.md`.

### The Evaluation Split — Two Audiences, Two Outputs

After any activity, there are two consumers of "how did it go?":

1. **The planner** needs structured analysis: what grammar was used, what
   errors occurred, what patterns are emerging, scores. This feeds its next
   decision and the session journal. It's internal — the learner never sees it.

2. **The learner** needs feedback that feels like a tutor talking, not a
   report card. Not "concepts_demonstrated: preterite (3/4 correct),
   engagement_quality: 0.7" but the tutor saying "Nice — you used tuve
   correctly for the first time in conversation! That's been tricky for
   you so that's real progress."

**The split:**

```
Activity completes
       │
       ▼
WORKER (fast): Generate structured evaluation
  → JSON: {corrections, scores, grammar_used, error_patterns, ...}
  → This is the RAW DATA. Goes to DB + planner.
       │
       ▼
PLANNER (smart): Read evaluation + session context + memory
  → Write the HUMAN feedback as a tutor message
  → The planner knows this is a breakthrough, knows what to celebrate,
    knows what not to belabor. It has the narrative.
  → Also decides: what activity comes next?
       │
       ▼
RENDER: Tutor message appears in chat
  → "Nice work! You got tuve right for the first time in free
     conversation — that's huge. You slipped back to 'teno' once
     near the end, which is totally normal. Let's keep pushing."
  → [Next activity card appears below]
```

**Why not have the worker write the feedback?** Because the worker doesn't
have the narrative context. It doesn't know that "tuve" has been the main
struggle for 3 sessions. It doesn't know that this learner appreciates
visible progress stats. It doesn't know that the learner is getting tired
and needs encouragement more than correction. The planner knows all of this
from the memory files and session history.

**Why not skip the worker evaluation and let the planner do everything?**
Speed and cost. The worker evaluation runs immediately after the activity
(fast, cheap). The planner processes the evaluation and makes its decision
in one call (smart, but only runs once per transition). If the planner had
to both evaluate grammar AND decide next steps AND write feedback, it would
be slower and more error-prone.

**The feedback template varies by context:**
- After conversation: highlight specific grammar moments, quote their words
- After drill: quick stats ("5/6, nice!"), mention specific misses
- After circumlocution: celebrate communication success first, grammar second
- After a frustrating activity: more encouragement, less analysis
- Session wrap-up: comprehensive stats + what improved + next time plan

### Why Markdown Over Database

1. **The planner reads prose, not SQL.** A language model understands
   "tener→tuve clicked in drills but not in free speech yet" infinitely
   better than `p_mastery=0.65, n_attempts=12, n_correct=8`.

2. **Lossy vs lossless.** A float loses the *story*. "0.45 mastery" could
   mean "never tried it" or "tried 20 times and keeps making the same
   mistake." The narrative preserves the why.

3. **Human-readable.** You (the developer, the learner) can open these
   files and immediately understand what's going on. No database queries,
   no dashboards. Just notes.

4. **The planner writes what it needs to read.** No translation layer.
   The model that makes pedagogical decisions is the same model that
   writes the notes. It knows what's relevant.

5. **Cheap to maintain.** Writing ~200 words of markdown at session end
   costs a few cents. Reading 2K tokens at session start costs a fraction
   of a cent.

### What Still Lives in the Database

The markdown memory doesn't replace *everything*. Some things are better
as structured data:

- **BKT mastery scores** — still useful for the mechanical scheduling
  layer (what's available to practice, unlock thresholds)
- **Session timing data** — timestamps, durations, response latencies
  (for energy estimation)
- **Activity results** — raw scores, specific errors (the journal
  summarizes these but the raw data is still useful for analytics)
- **Planner decision log** — for debugging and improvement

Think of it as two layers:
- **Database:** the mechanical layer (what happened, when, scores)
- **Markdown:** the intelligence layer (what it means, what to do about it)

The planner reads the markdown. The analytics/debugging reads the database.
Both exist, serving different purposes.

---

## Hybrid Mastery: BKT + Narrative Assessment

The system uses two complementary mastery tracking approaches. Neither
replaces the other — they serve different purposes and together give a
richer picture than either alone.

### Layer 1: BKT (Mechanical Accuracy)

Bayesian Knowledge Tracing gives a single number (0.0–1.0) per concept,
updated deterministically on each right/wrong answer. It's great for:

- **Progress bars and unlock thresholds** — needs a number
- **Concept graph traversal** — "prerequisites met" requires p_mastery >= 0.90
- **Drill-type activities** — clear right/wrong, maps cleanly to BKT
- **Consistency** — same inputs always produce same outputs

But BKT is blind to context. It can't distinguish "got tuve right in a
fill-the-blank drill" from "spontaneously used tuve mid-conversation."
The second is far more impressive pedagogically.

### Layer 2: Planner's Narrative Assessment (Communicative Competence)

The planner's grammar_notes.md captures qualitative mastery through
dated evidence entries with statuses (WEAK / IN_PROGRESS / SOLID /
AVOIDANCE / NOT_YET_INTRODUCED). The planner can write things like:

> "Used ser/estar correctly in free conversation twice, but still
> confuses them in translation exercises. Avoids estar entirely when
> talking about feelings."

This captures what BKT cannot: transfer ability, avoidance patterns,
contextual competence, self-correction behavior.

### How They Work Together

The planner sees **both** layers in its context:

1. **CURRICULUM STATUS** section — BKT numbers from concept_knowledge table
2. **GRAMMAR STATUS** section — narrative notes from grammar_notes.md

The planner uses BKT as the "floor" (minimum evidence threshold) and its
own narrative assessment as the decision-maker:

- If BKT says 0.92 mastery on ser/estar but grammar_notes say "avoids
  estar in free speech, only gets it right in drills" → keep working on it
- If BKT says 0.45 on colors but grammar_notes say "gets colors right
  in conversation, bombed the drill due to spelling" → less urgent
- If BKT says 0.0 (never attempted) and grammar_notes say nothing →
  check prerequisites, consider introducing it

**BKT tracks mechanical accuracy. The planner tracks communicative
competence. You want both.**

### Write-Back: Activities → BKT

When tutor activities complete, results flow back to BKT automatically:

- **Translation challenge**: each sentence → one BKT attempt
  (correct = communicated_successfully)
- **Conjugation drill**: each item → one BKT attempt (exact match)
- **Conversation**: no direct BKT write-back — too fuzzy for binary
  scoring. The planner updates grammar_notes instead.
- **Circumlocution**: communication_score > 0.5 → correct attempt

This keeps BKT numbers fresh even when the learner only uses the tutor
(not the original flow system). The concept graph, tier unlocks, and
progress views all stay accurate.

### The CURRICULUM STATUS Section

Injected into the planner's context alongside the three markdown files.
Built from the concept graph + BKT data at session start:

```
## CURRICULUM STATUS

Current tier: 2 (Basic Grammar) — 60% complete
Tier 1 (Foundations): 5/5 mastered ✅
Tier 2 (Basic Grammar): 3/5 mastered, 2 in progress
  🔄 articles_definite — 0.65 mastery (8 attempts)
  🔄 present_tense_regular — 0.72 mastery (12 attempts)

Next available: adjective_agreement, present_tense_irregular
Avoidance alert: articles_definite (8 attempts, 0.65 mastery)
```

Compact (~300-500 tokens). Focuses on in-progress and stuck concepts.
Mastered concepts shown as counts only. The planner uses this to pick
the right concept, then uses grammar_notes to decide the approach.

---

## The Planner System Prompt

This is the "brain" of the system. It needs to be carefully crafted.

```
You are an expert Spanish language tutor for DELE A2 preparation.

LEARNER PROFILE:
{session_context}

YOUR ROLE:
Decide what learning activity to give the learner next. You have tools that
create interactive exercises. Pick the right tool based on:

1. WHAT THEY NEED: Look at weak_concepts. Target the biggest gap.
2. ACTIVITY VARIETY: Don't repeat the same activity type 3x in a row.
   Mix conversations, drills, reading tasks, writing tasks.
3. ENERGY LEVEL: If response times are increasing or errors are spiking,
   switch to something lighter (conversation > drill). If they're on fire,
   push harder.
4. DELE A2 COVERAGE: Make sure they get exposure to all exam task types
   over time (not all in one session).
5. INTERESTS: Theme activities around their interests when possible.

PEDAGOGICAL PRINCIPLES:
- Production over recognition: Make them WRITE and SPEAK, not just click.
- Interleaving: Mix concepts that are easily confused (preterite vs imperfect).
- Spaced repetition: Revisit mastered concepts occasionally.
- Scaffolding: Start supported, remove support as they improve.
- The "struggle zone": Activities should be hard enough to require thinking
  but not so hard they shut down. Target ~70-80% success rate.

CALL ONE TOOL. Return your reasoning briefly, then the tool call.
```

---

## Session Rhythm — The Chat-First Interaction Model

The entire session lives inside a **chat interface**. The tutor talks to you
in English (it's a tutor, not a conversation partner), and activities get
embedded inline within the chat. Think of it like iMessage where a tutor
sends you interactive cards between their messages.

### Why Chat-First?

1. The learner has agency — they can redirect, ask questions, say "this is too hard"
2. The tutor can explain, encourage, and contextualize naturally
3. Activities feel like part of a conversation, not a disconnected quiz screen
4. The tutor's personality and pedagogical style come through

### The Three-Phase Session Shape

Every session has a natural arc. The planner operates within this structure,
not as a random activity picker.

#### Phase 1: Opening Check-In (1-2 minutes)

The tutor reads the learner's state and proposes a focus. This is a real
conversation — the learner can agree or redirect.

```
TUTOR: Hey! Last session you were working on irregular preterite — you
       nailed ir and hacer but tener was still tripping you up. I want to
       keep pushing on that today. We'll start by chatting about what you
       did yesterday, then do some quick drills. Sound good?

YOU:   Yeah, but I also want to practice describing things — like telling
       a story about something that happened.

TUTOR: Love it. Let's do that — we'll chat with Marta about your weekend,
       then I'll give you a picture to describe. Both will force you to
       use preterite in longer chunks. Let's go.
```

**Implementation:** The planner's FIRST call is always `propose_session_plan`.
This tool generates a brief plan and presents it as a tutor message. The
learner's response gets fed back to the planner, which adjusts the plan.
Then activities begin.

```python
# New tool
def propose_session_plan(
    focus_concepts: list[str],     # what to target
    suggested_activities: list[str], # conversation, drill, image_desc
    session_goal: str,              # "Build preterite automaticity"
    personalized_note: str,         # "Last time tener was the weak spot"
) -> SessionPlan:
    ...
```

#### Phase 2: Core Practice Loop (15-25 minutes)

Activities flow naturally with minimal interruption. The tutor introduces
each activity with a brief message, then the interactive component appears
inline in the chat.

```
TUTOR: Alright, Marta wants to know about your weekend. Chat with her —
       try to use past tense for everything, even if you have to think
       about it. Don't worry about being perfect.

┌─────────────────────────────────────────────────┐
│  💬 Marta                                        │
│  "¡Oye! ¿Qué tal el finde? Yo fui a un          │
│   concierto increíble el sábado."                │
│                                                   │
│  [Your message...]                    [Send]      │
└─────────────────────────────────────────────────┘

[... 4 turns of conversation ...]

TUTOR: Nice! You got 3 out of 4 preterite forms right. You said "yo
       teno" instead of "tuve" — that one keeps coming up. Let's drill
       it. Quick round — just type the correct form.

┌─────────────────────────────────────────────────┐
│  ⚡ Conjugation Drill — Pretérito               │
│                                                   │
│  yo / tener  →  [________]                        │
│                                                   │
│  3 of 6                          ⏱ no time limit  │
└─────────────────────────────────────────────────┘

[... drill completes ...]

TUTOR: Better! 5/6. You got tuve right this time. Now try using it
       in a real sentence — describe what's happening in this photo.

┌─────────────────────────────────────────────────┐
│  🖼 Describe this scene                          │
│                                                   │
│  [Image: family at a restaurant]                 │
│                                                   │
│  "Tell the story of what happened at this        │
│   dinner. Use at least 3 sentences in the past." │
│                                                   │
│  [Your description...]              [Submit]      │
└─────────────────────────────────────────────────┘
```

**Key cadence rules for the planner:**
- Don't ask "what do you want to do next?" between activities — just flow
- DO give brief feedback between activities (1-2 sentences, in the chat)
- Alternate between production activities (conversation, writing) and
  focused drills (conjugation, MCQ)
- If the learner types a message outside an activity (asks a question,
  says something), the tutor responds naturally and then continues

#### Phase 3: Wrap-Up (1-2 minutes)

```
TUTOR: Great session! Here's your snapshot:

       📊 Preterite forms used: 14 (11 correct, 79%)
       💪 Improved: tener → tuve (got it 3/4 times today vs 0/3 last time)
       ⚠️  Still tricky: poder → pude (missed twice)
       🌟 You explained a complex idea about your job using simple vocab
          — that's exactly the skill DELE A2 tests.

       Next time we'll hit poder/pude harder and try a WhatsApp
       message exercise. ¡Buen trabajo!
```

### The "Express Complex Ideas" Exercise Type

This deserves its own tool. The learner gets a complex English prompt and
must express it in Spanish using only the vocabulary they know. This is
**circumlocution practice** — a core DELE A2 skill.

```python
# New tool: show_circumlocution_challenge
{
  "prompt_en": "Explain to Marta why you changed jobs last year. You
                were unhappy with your boss and wanted more money, but
                you also missed your old colleagues.",
  "target_grammar": "preterite",
  "vocabulary_level": "A2",
  "evaluation_focus": "communication_success"  # not just grammar accuracy
}
```

The evaluation doesn't just check grammar — it checks whether the learner
successfully communicated the idea, even if they used workarounds like
"my boss was not good" instead of "my boss was demanding." That resourcefulness
IS the skill.

### When the Learner Asks Questions

The chat format naturally supports this. If the learner types "wait, when
do I use tuve vs tenía?" outside of an activity, the planner receives this
and can:

1. Answer the question directly (tutor message)
2. Call `show_teach_card` to show a mini-lesson
3. Call `start_conversation` with the confused concept as target
4. Any combination

The planner decides based on context — if they're mid-session and making
good progress, a quick answer and move on. If they seem genuinely confused,
pause for a teach moment.

### Cadence Control — Avoiding Question Fatigue

Rules the planner follows to maintain good session flow:

1. **Never ask 2 meta-questions in a row** ("How was that?" → "Ready for
   the next one?"). Just flow.
2. **Only check in at natural breakpoints** — after a full activity, not
   mid-drill.
3. **Limit learner choices to max 1 per session** — the opening check-in.
   After that, the tutor leads.
4. **Feedback is brief and specific** — "Nice, tuve was right this time!"
   not a paragraph of analysis.
5. **Session plan is invisible** — the learner doesn't see "Activity 3 of 7".
   It feels organic.

### Distress Signal — Worker-Level Early Escape

Activities like conversations and drills run independently from the planner for
multiple turns. But sometimes the learner is struggling badly and the activity
should end early rather than grinding through to completion. The worker detects
this and sends a **distress signal** back to the planner.

**How it works:**

Every worker response (conversation turn, drill answer evaluation) returns a
`status` field alongside its normal output:

```python
@dataclass
class WorkerTurnResult:
    """What the worker returns after each turn within an activity."""
    response: str               # The normal output (AI message, evaluation, etc.)
    should_continue: bool       # Can we keep going?
    distress_signal: DistressSignal | None  # Set when the learner is struggling

@dataclass
class DistressSignal:
    """Worker flags that the learner needs help beyond what it can provide."""
    reason: str                 # What triggered it
    severity: str               # "mild" | "moderate" | "severe"
    evidence: list[str]         # Specific observations
    suggested_pivot: str | None # Worker's best guess at what might help
```

**Trigger conditions** (worker monitors these each turn):

```
MILD (worker handles itself, logs for planner):
  - Learner takes >30 seconds to respond (hesitation)
  - One turn mostly in English
  - Minor grammar pattern repeating (same error 2x)

MODERATE (early exit, return to planner):
  - 2+ consecutive turns mostly in English
  - Learner responses getting shorter (disengagement)
  - Same grammar error 3+ times despite worker recasting
  - Learner explicitly says "I don't understand" / "no sé"

SEVERE (immediate exit, planner gets full context):
  - 3+ consecutive English turns
  - Learner says "this is too hard" or similar frustration
  - Learner stops responding (>60 second gap)
  - Conversation has devolved into single-word answers
```

**What happens on a moderate/severe signal:**

```
Conversation turn 3 of 4:
  Learner: "I don't know how to say it... I went? yo fue?"
  Worker detects: 3rd preterite error, learner expressing frustration
       │
       ▼
  Worker returns:
    response: "No te preocupes — ¡estás muy cerca!" (encouraging)
    should_continue: false  ← EARLY EXIT
    distress_signal:
      reason: "repeated_grammar_failure"
      severity: "moderate"
      evidence: ["said 'yo fue' (ir→fui error)", "3rd preterite error",
                 "expressed frustration: 'I don't know how to say it'"]
      suggested_pivot: "teach_card for ir preterite conjugation"
       │
       ▼
  Planner receives distress signal + conversation history
  Planner decides:
       │
       ├──▶ show_teach_card(concept="preterite_irregular",
       │    focus="ir → fui — the full conjugation",
       │    context="Learner just struggled with this in conversation.
       │             Keeps saying 'yo fue' instead of 'yo fui'.
       │             Show the pattern clearly.")
       │
       └──▶ Tutor message: "Hey, let's pause for a sec. The ir forms
            are tricky — here's how they work..."
       │
       ▼
  After teach card:
  Planner decides: retry conversation at lower difficulty?
  Or switch to a conjugation drill to build the form in isolation first?
  (The planner has the intelligence to choose the right recovery path.)
```

**The key insight:** The worker doesn't decide what to do about the struggle —
it just reports it. The planner decides the recovery strategy because it has the
full learner context (memory files, session history, what's been tried before).
Maybe this learner has already seen a teach card for this concept today, so the
planner tries a drill instead. Maybe the learner's energy is low and the planner
switches to something lighter entirely. The worker just raises the flag.

**Implementation in conversation worker:**

```python
async def respond_to_user(message: str, session: ConversationSession,
                          worker_briefing: str) -> WorkerTurnResult:
    # Normal conversation response
    response = await generate_response(message, session, worker_briefing)

    # Distress detection (runs on every turn)
    signal = detect_distress(
        current_message=message,
        turn_history=session.turns,
        target_concept=session.concept,
    )

    return WorkerTurnResult(
        response=response,
        should_continue=signal is None or signal.severity == "mild",
        distress_signal=signal,
    )
```

---

## Visual Design Specifications for Tool Cards

Every tool that renders a UI card in the chat needs a clear visual specification
in its tool definition. The worker generates structured JSON, and a Jinja template
renders it into a visually consistent card. This section defines the shared design
language across all cards.

### Shared Card Design Principles

1. **Cards live inside the chat.** They appear inline between tutor messages,
   not as separate screens. They should feel like rich messages, not app pages.

2. **Consistent structure.** Every card has:
   - A type icon + title bar (e.g., "💬 Conversation with Marta", "⚡ Conjugation Drill")
   - A content area (varies by card type)
   - An input area (text field, buttons, etc.)
   - A subtle border/background that distinguishes it from tutor messages

3. **Mobile-first sizing.** Cards should work on a phone screen. No horizontal
   scrolling, no tiny text. Max width ~600px, centered in the chat.

4. **Tailwind styling.** All cards use Tailwind utility classes. Consistent
   color palette: primary actions in indigo, success in green, errors in red,
   card backgrounds in slate-50, borders in slate-200.

5. **State transitions.** Cards have states:
   - Active (learner is working on it)
   - Completed (shows results, greyed out slightly)
   - Collapsed (after moving to next activity, shows just the title + score)

### Card-Specific Visual Formats

Each tool's parameters section now includes a `Visual Format` block showing
what the rendered card looks like. The worker returns structured JSON and the
Jinja template handles the rendering. See individual tool definitions for their
specific visual formats.

**When building new tools**, always define:
- What the card looks like in its active state
- What structured JSON the worker returns
- How the card transitions to its completed state
- What the collapsed summary looks like in the chat history

---

## Integration with Existing Code

The beauty of this design is that **most of the existing code survives**.
We're wrapping it, not replacing it.

### What stays as-is:
- `conversation.py` — ConversationEngine becomes the implementation of `start_conversation` tool
- `evaluation.py` — Used by the agent to evaluate conversation results
- `bkt.py` — Still tracks concept mastery (mechanical layer)
- `personas.py` — Still loads personas for conversation tool
- `prompts.py` + `prompts.yaml` — Still manages worker prompt templates
- `concepts.py` — Still the concept graph
- `flow_ai.py` — MCQ generation becomes `show_mcq` tool implementation

### What gets replaced by narrative memory:
- `memory.py` — Persona memories → learner_profile.md (richer, pedagogically aware)
- `interest.py` — Float-based interest scores → Interests section in learner_profile.md
  (the planner now understands *why* a topic works, not just a 0.7 score)
- `persona_engagement` table — Engagement tracking → session_journal.md
  (the planner reads "Marta persona is working really well" not "engagement: 0.8")

### What changes:
- `flow.py` — The deterministic scheduler gets replaced by the agent loop
- `flow_routes.py` — Routes change to support the agent loop pattern
- `flow_db.py` — Needs new tables for agent session state, activity results

### What's new:
- `tutor_agent.py` — The agent loop: calls planner, executes tools, manages state
- `tutor_tools.py` — Tool definitions and implementations
- `tutor_context.py` — Builds session context for the planner
- New templates: `conjugation_drill.html`, `translation_challenge.html`,
  `image_description.html`, `whatsapp_task.html`, `agent_feedback.html`
- New route group: `/tutor/...` (separate from `/flow/...` so both can coexist)

---

## HTMX Integration Pattern

The agent loop needs to work with HTMX's swap model. Here's the pattern:

### 1. Session Start
```
GET /tutor → renders tutor.html (empty activity area + sidebar)
                  ↓
              JS: fetch /tutor/next (on page load)
                  ↓
          Server: planner decides first activity → renders partial
                  ↓
              HTMX swaps partial into #activity-area
```

### 2. During Activity (e.g., conversation)
```
User types message → POST /tutor/conversation/respond
                          ↓
                     Server: ConversationEngine.respond_to_user()
                          ↓
                     Returns HTMX partial (new message bubble)
                          ↓
                     [Conversation continues until max_turns]
                          ↓
                     POST /tutor/conversation/complete
                          ↓
                     Server: evaluate, feed results to planner
                          ↓
                     Planner decides next activity → renders next partial
                          ↓
                     HTMX swaps new activity into #activity-area
```

### 3. Transition Between Activities
```
Activity completes → POST /tutor/complete
                          ↓
                     Server: record results, build updated context
                          ↓
                     Planner call (may take 1-2 sec)
                          ↓
                     [Optional: show_feedback tool first]
                          ↓
                     Next activity partial rendered
                          ↓
                     HTMX swaps in new activity
```

The key insight: **within an activity, it's all fast worker calls** (no planner
latency). The planner only runs at **transition points** between activities.

---

## Speed Budget

| Operation | Model | Expected Latency | When |
|---|---|---|---|
| Planner decision | gpt-5.2 | 1-3 sec | Between activities (~5-10x/session) |
| Conversation response | gpt-5.2-mini | 0.3-1 sec | Each user turn |
| Worker evaluation | gpt-5.2-mini | 0.3-1 sec | After activity completes |
| MCQ evaluation | Local (no LLM) | <50ms | Each MCQ answer |
| Conjugation drill eval | Local / gpt-5.2-nano | <100ms | Each drill answer |
| Translation evaluation | gpt-5.2-mini | 0.3-1 sec | Each sentence |
| Image description eval | gpt-5.2-mini | 0.3-1 sec | After submission |
| Grammar classification | gpt-5.2-nano | <200ms | Lightweight checks |

### Prefetch Strategy — Hiding Planner Latency

The planner's 1-3 second latency should be **invisible** to the learner.
The trick is to start the planner call BEFORE the current activity finishes,
so the next activity is already decided by the time the learner is ready.

**Principle: the planner should always be one step ahead.**

#### Strategy 1: Speculative prefetch on final turn

When a conversation hits its last turn (turn 4 of 4), the server knows it's
about to end. Fire the worker evaluation AND the planner call **in parallel**
while the final AI response is being generated.

```
Turn 4 (final):
  User sends message
       │
       ├──▶ WORKER: generate AI response (0.3-1s)
       │
       └──▶ Async: WORKER eval (partial, based on turns 1-3)
                 │
                 └──▶ PLANNER: decide next activity (1-3s)
                      (uses partial eval — 3/4 turns is enough signal)

  By the time learner reads the final AI response... planner is done.
  Conversation "complete" → feedback + next activity renders INSTANTLY.
```

#### Strategy 2: Prefetch during drill tail end

During a conjugation drill, by item 5 of 6 you have enough signal. Fire
the planner with partial results. If item 6 changes the picture, you can
invalidate and re-call (rare), but 90% of the time 5/6 is the same story
as 6/6.

```
Drill item 5 answered:
  Score so far: 4/5
       │
       └──▶ Async: PLANNER(partial_results="4/5, missed tener")
                   (runs while learner does item 6)

  Item 6 answered → drill complete
  Planner result already waiting → instant transition
```

#### Strategy 3: Feedback card as a buffer

The planner returns TWO things in one call: the feedback message AND the
next tool call. Render the feedback immediately. While the learner reads
"Nice, 5/6! You got tuve right this time" (2-4 seconds of reading time),
the next activity's template and content are loading in the background.

```
Planner returns:
  {
    "tutor_message": "Nice! 5/6...",     ← render immediately
    "next_tool": "start_conversation",    ← begin loading
    "next_params": {...}                  ← generate opener async
  }

  Learner reads feedback (2-4 sec)
       │
       └──▶ Async: WORKER: generate_opener() for next conversation

  Learner scrolls down → conversation card already rendered with opener
```

#### Strategy 4: Optimistic background precomputation

At session start, after the opening check-in, the planner can return a
**tentative session plan** — not just the next activity, but the next 2-3
activities as a ranked list. The server pre-generates content for activity #2
while activity #1 is running. If activity #1 results change the plan, the
pre-generated content may get discarded, but the hit rate should be high
(~80%+ of the time, the plan holds).

```
Session start:
  PLANNER returns:
    1. start_conversation(marta, preterite)  ← DO THIS NOW
    2. show_conjugation_drill(tener, poder)  ← LIKELY NEXT
    3. show_image_description(vacation)      ← MAYBE AFTER

  While activity 1 runs:
    └──▶ Async: pre-generate drill items for activity 2
    └──▶ Async: pre-select image for activity 3
```

#### Implementation

Use Python's `asyncio.create_task()` in FastAPI to fire planner calls
without blocking the response. Store the prefetched result in the
TutorSession object (in-memory) or a short-lived cache.

```python
# In tutor_routes.py, during final conversation turn:
async def conversation_respond(...):
    # Normal response
    result = engine.respond_to_user(...)

    # If this is the last turn, fire planner prefetch
    if turn_number >= max_turns:
        session.prefetch_task = asyncio.create_task(
            session.plan_next_action(activity_result=partial_eval)
        )

    return render_message(result)

async def conversation_complete(...):
    # Planner result may already be ready
    if session.prefetch_task:
        planner_result = await session.prefetch_task  # instant or near-instant
    else:
        planner_result = await session.plan_next_action(...)  # fallback

    return render_feedback_and_activity(planner_result)
```

**Target: zero perceived latency between activities.** The learner should
feel like the tutor always knows what's next, without ever seeing a spinner.

---

## Database Additions

```sql
-- Agent session state
CREATE TABLE tutor_sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    planner_model TEXT,
    session_context_json TEXT,   -- serialized TutorSessionContext
    activities_json TEXT         -- log of all activities + results
);

-- Individual activity records
CREATE TABLE tutor_activities (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    activity_type TEXT NOT NULL,  -- conversation, mcq, drill, etc.
    tool_params_json TEXT,        -- what the planner asked for
    result_json TEXT,             -- what happened
    started_at TEXT NOT NULL,
    completed_at TEXT,
    score REAL,                   -- 0.0 - 1.0
    concept_id TEXT,
    FOREIGN KEY (session_id) REFERENCES tutor_sessions(id)
);

-- Planner decision log (for debugging and improvement)
CREATE TABLE planner_decisions (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    context_json TEXT,            -- what the planner saw
    reasoning TEXT,               -- planner's explanation
    tool_name TEXT,               -- what it chose
    tool_params_json TEXT,        -- with what parameters
    created_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES tutor_sessions(id)
);
```

---

## Model Strategy — GPT-5.2 Family

Single provider (OpenAI), single SDK, three tiers:

```yaml
# In data/prompts.yaml
tutor:
  planner:
    model: "gpt-5.2"          # Flagship. The brain.
    temperature: 0.3
    max_tokens: 1500

models:
  respond: "gpt-5.2-mini"     # Conversation, content gen
  evaluation: "gpt-5.2-mini"  # Structured eval after activities
  grammar_check: "gpt-5.2-nano"  # Ultra-cheap classification
  classification: "gpt-5.2-nano" # Intent detection, routing
```

**Why single provider:** No Anthropic SDK dependency, no provider-switching
logic, one API key, one billing dashboard. The existing `_get_client()` from
`flow_ai.py` works for everything — planner and workers alike. If OpenAI
ships something better, swap one string in the YAML.

**Cost structure:**
- gpt-5.2 (planner): ~5-10 calls/session, 1-2K tokens each. The expensive one.
- gpt-5.2-mini (workers): ~20-40 calls/session, 200-500 tokens each. Cheap.
- gpt-5.2-nano (classification): ~10-20 calls/session, tiny. Almost free.

---

## Phase 1 Implementation Plan

Don't build everything at once. Ship the agent loop with 3-4 tools first.

### Phase 1a: Agent Loop + Conversation Tool
1. Build `tutor_agent.py` with the planner loop
2. Wire up `start_conversation` as the first tool (wraps existing ConversationEngine)
3. Build `tutor_context.py` to provide session state to planner
4. New routes at `/tutor/...`
5. Simple `tutor.html` template with activity area

**This alone is valuable** — even with just one tool, the planner adds
intelligence by choosing the right concept, topic, persona, and difficulty
for each conversation. It's already smarter than the current `flow.py`
scheduler.

### Phase 1b: + Conjugation Drill + MCQ
6. Build `show_conjugation_drill` tool + `conjugation_drill.html` template
7. Wire up `show_mcq` tool (wraps existing MCQ system)
8. Planner now has 3 activity types to mix

### Phase 1c: + Translation Challenge + Feedback
9. Build `show_translation_challenge` tool + template
10. Build `give_feedback` tool + template
11. The planner can now do real interleaving: converse → drill → translate → feedback

### Phase 2: DELE A2 Task Types
12. `show_image_description` tool + template
13. `show_whatsapp_task` tool + template
14. DELE-specific planner instructions

### Phase 3: Advanced
15. Voice input/output (speech-to-text, text-to-speech)
16. Adaptive difficulty tuning based on response timing
17. Spaced repetition scheduling across sessions
18. Export practice history for DELE prep review

---

## Open Questions

1. **Planner API format**: Use OpenAI function calling format? Anthropic tool_use?
   Or a generic JSON schema that we translate per provider?
   → **Recommendation:** Use OpenAI function calling format as the internal standard,
   translate to Anthropic format when needed. Most examples/docs use this format.

2. **Conversation handoff**: ~~How does the planner get notified of mid-conversation
   issues?~~ **RESOLVED** — See "Distress Signal — Worker-Level Early Escape" section.
   Workers return a `DistressSignal` on each turn. Mild signals are logged, moderate/
   severe signals trigger early exit back to the planner with full context. The planner
   decides recovery strategy (teach card, drill, lower difficulty, activity switch).

3. **Image generation**: Stock images vs AI-generated? Stock is faster and cheaper.
   AI-generated is more flexible and can be themed.
   → **Recommendation:** Start with curated stock images tagged by theme/tense.
   Add AI generation later as an enhancement.

4. **State persistence across sessions**: Should the planner remember what happened
   last session?
   → **Recommendation:** Yes. The `tutor_sessions` table + BKT state gives the
   planner enough context. Build a "session summary" that persists and gets
   included in the next session's context.

---

## Why This Approach Works

1. **Separation of concerns**: The planner thinks about pedagogy. Workers handle
   execution. The frontend handles rendering. Clean layers.

2. **Speed where it matters**: Sub-second responses during activities (worker calls).
   The planner's 1-3 second latency is hidden behind transition UIs.

3. **Incrementally buildable**: Each new tool is an independent addition. The
   planner automatically learns to use new tools as they appear.

4. **Existing code reuse**: 80%+ of your current codebase is preserved. The
   conversation engine, BKT, personas, memory — all still valuable.

5. **Provider flexibility**: Swap models anytime. Use the best model for each
   job. Not locked into one provider.

6. **Debuggable**: The `planner_decisions` table logs every decision with
   reasoning. You can replay sessions and understand why the agent did what it did.

7. **The "smart engine" you described**: This IS the prototype for the engine.
   The HTMX frontend is replaceable — swap it for a React Native app later and
   the agent loop + tools are identical. The intelligence is in the backend.
