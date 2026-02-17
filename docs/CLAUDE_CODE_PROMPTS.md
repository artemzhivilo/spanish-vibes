# Claude Code Prompts — Building the Agent Tutor

Use these prompts in sequence with Claude Code. Each one builds on the
previous. Read `docs/AGENT_ARCHITECTURE.md` first — that's the blueprint.

---

## Prompt 0: Context Setting

Paste this at the start of every Claude Code session so the model
understands the project:

```
Read docs/AGENT_ARCHITECTURE.md — this is the architecture for what we're
building. Also read src/spanish_vibes/conversation.py,
src/spanish_vibes/flow_ai.py, src/spanish_vibes/flow.py,
src/spanish_vibes/prompts.py, and data/prompts.yaml to understand the
existing codebase. We're building an agent-based tutor on a new branch
called `agent-tutor`. The existing flow system stays intact — we're adding
a parallel `/tutor/` route group.
```

---

## Prompt 1: Tutor Agent Core Loop

```
Build the core agent loop in src/spanish_vibes/tutor_agent.py.

This is the central orchestrator for the new tutor system. It should:

1. Define a TutorSession class that:
   - Holds session state (session_id, user_id, activities completed,
     current activity, message history)
   - Reads the learner's markdown memory files at session start
     (data/learners/{user_id}/learner_profile.md,
      data/learners/{user_id}/session_journal.md,
      data/learners/{user_id}/grammar_notes.md)
   - Falls back gracefully if memory files don't exist yet (new learner)

2. Define a `plan_next_action()` method that:
   - Builds a context prompt from the markdown memory files + current
     session history (activities done, scores, what just happened)
   - Calls the planner model (configurable — Claude Sonnet or GPT-4o)
     with tool definitions
   - Parses the tool call response
   - Returns a TutorAction dataclass with tool_name, params,
     worker_briefing, and tutor_message (what the tutor says to the
     learner before the activity starts)

3. Define tool schemas as OpenAI function-calling format dicts.
   Start with these tools only:
   - propose_session_plan
   - start_conversation
   - show_conjugation_drill
   - give_feedback
   - end_session
   - update_session_journal
   - update_grammar_notes

4. Support both Anthropic and OpenAI as planner providers. Read the
   provider config from data/prompts.yaml under a new `tutor:` section.
   Use the existing _get_client() pattern from flow_ai.py for OpenAI,
   and add an anthropic client for Claude.

Keep it clean — no route handling, no HTML. Just the agent logic.
The planner system prompt should follow what's in AGENT_ARCHITECTURE.md
under "The Planner System Prompt".

Don't forget: pip install anthropic if needed.
```

---

## Prompt 2: Tool Implementations

```
Build src/spanish_vibes/tutor_tools.py — the implementations for each
tool the planner can call.

Read docs/AGENT_ARCHITECTURE.md for the full tool definitions.

Each tool is a function that:
- Takes the tool params (from the planner's function call) + the
  TutorSession context
- Executes the activity (may involve Tier 2 LLM calls)
- Returns a ToolResult with:
  - html: str (the HTMX partial to render)
  - result_summary: str (what the planner sees about how it went)
  - activity_data: dict (raw data for the database)

Implement these tools for Phase 1:

1. `propose_session_plan` — Format the planner's session plan as a
   tutor chat message. Return HTML for a chat bubble with the plan.

2. `start_conversation` — Wrap the existing ConversationEngine.
   - Call generate_opener() with the specified persona, topic, concept
   - Inject worker_briefing into the conversation guardrails
   - Return the conversation UI partial (reuse the existing
     flow_conversation.html template pattern)
   - The conversation runs independently for N turns via separate
     routes, then reports back

3. `show_conjugation_drill` — NEW activity type.
   - Generate drill items: subject + infinitive → learner types conjugation
   - For now, use a hardcoded verb conjugation table (no LLM needed)
   - Build a simple HTMX partial that shows one item at a time
   - Evaluate answers locally (string match with accent normalization)

4. `give_feedback` — Simple: render the planner's message as a tutor
   chat bubble, optionally with stats.

5. `end_session` — Render wrap-up card with session stats.

6. `update_session_journal` — Append entry to the learner's
   session_journal.md file. Create the file/directory if it doesn't exist.

7. `update_grammar_notes` — Update the learner's grammar_notes.md file.

For the conjugation drill, create a verb table in
data/verb_conjugations.yaml with at least these verbs in preterite:
ir, hacer, tener, poder, estar, ser, querer, venir, decir, poner.
Include all persons (yo, tú, él/ella, nosotros, ellos/ellas).
```

---

## Prompt 3: Routes and Templates

```
Build the route layer and templates for the tutor system.

Read docs/AGENT_ARCHITECTURE.md, especially the "HTMX Integration Pattern"
and "Session Rhythm" sections.

1. Create src/spanish_vibes/tutor_routes.py with a FastAPI router
   mounted at /tutor/:

   GET /tutor
   - Main tutor page. Renders tutor.html with an empty chat area.
   - On page load, HTMX auto-fetches /tutor/start to begin.

   POST /tutor/start
   - Creates a TutorSession, calls plan_next_action() for the first
     time (which should call propose_session_plan).
   - Returns the tutor's opening message as an HTMX partial appended
     to the chat.

   POST /tutor/respond
   - Learner sends a message (either a chat reply or an activity result).
   - If mid-activity: route to the activity handler.
   - If between activities: feed to the planner for next decision.
   - Returns the next chunk of chat (tutor response + possibly a new
     activity card).

   POST /tutor/conversation/respond
   - Handles conversation turns within a start_conversation activity.
   - Uses existing ConversationEngine.respond_to_user()
   - Returns message bubble partial.

   POST /tutor/conversation/complete
   - Conversation finished. Evaluates results, feeds to planner.
   - Returns feedback + next activity.

   POST /tutor/drill/answer
   - Handles conjugation drill answers one at a time.
   - Returns feedback for current item + next item (or drill complete).

   POST /tutor/drill/complete
   - Drill finished. Feeds results to planner.

2. Create templates:

   templates/tutor.html
   - Full page with chat-style layout. Dark theme matching existing app.
   - Scrollable message area (#tutor-chat).
   - Input bar at bottom for learner messages.
   - Messages alternate: tutor (left, different color) and learner (right).
   - Activity cards render inline in the chat flow.

   templates/partials/tutor_message.html
   - Single tutor chat bubble. Takes message text.

   templates/partials/tutor_activity_conversation.html
   - Conversation card embedded in chat. Reuse existing conversation UI
     patterns (persona avatar, message bubbles, clickable word translation)
     but styled to fit within the chat layout.

   templates/partials/tutor_activity_drill.html
   - Conjugation drill card. Shows: subject + infinitive, input field,
     submit button, progress (3 of 8), feedback on previous answer.

   templates/partials/tutor_feedback.html
   - Session stats card with score, improvements, weak spots.

3. Register the router in the main app (app.py or wherever the
   FastAPI app is created).

The key UX principle: everything is a chat message or an inline card.
No page navigations. The tutor talks, activities appear, results show,
tutor reacts, next activity appears. All via HTMX swaps appending to
#tutor-chat.
```

---

## Prompt 4: Narrative Memory System

```
Build the narrative memory system for the tutor.

Read docs/AGENT_ARCHITECTURE.md, "Learner Memory — Narrative Context"
section for the full design.

1. Create src/spanish_vibes/tutor_memory.py with:

   - get_learner_dir(user_id) → Path to data/learners/{user_id}/
   - ensure_learner_dir(user_id) → Creates dir if needed

   - read_learner_profile(user_id) → str (contents of learner_profile.md,
     or a default template for new learners)
   - read_session_journal(user_id, last_n=5) → str (last N entries from
     session_journal.md, or empty string)
   - read_grammar_notes(user_id) → str (contents of grammar_notes.md,
     or a starter template)

   - write_learner_profile(user_id, content: str) → None
   - append_session_journal(user_id, entry: str) → None
   - write_grammar_notes(user_id, content: str) → None

   - build_planner_context(user_id) → str
     Combines all three files into a single context block formatted
     for the planner system prompt. Includes headers like:
     "## LEARNER PROFILE\n{profile}\n\n## RECENT SESSIONS\n{journal}\n\n## GRAMMAR STATUS\n{notes}"

2. Create a default template for new learners in
   data/templates/new_learner_profile.md:
   ```
   # Learner Profile
   Updated: {date}

   ## Level & Stage
   New learner. Level not yet assessed.

   ## Current Focus
   Initial assessment needed.

   ## Learning Style
   Not yet known — observe during first 2-3 sessions.

   ## Interests & Life Context
   Not yet known — discover through conversation.

   ## Personality Notes
   Not yet known.
   ```

3. Create data/templates/new_grammar_notes.md with a starter template
   that has empty sections for the main A2 grammar areas.

4. Update tutor_agent.py to use tutor_memory.build_planner_context()
   when building the planner prompt, and to call the memory write
   functions when the planner calls update_session_journal or
   update_grammar_notes tools.

The memory files live on disk in data/learners/{user_id}/ — NOT in the
database. They're human-readable markdown. The planner reads them as
context and writes them as output.
```

---

## Prompt 5: Database Layer

```
Add the tutor database tables to src/spanish_vibes/flow_db.py (or create
a new src/spanish_vibes/tutor_db.py if cleaner).

Read docs/AGENT_ARCHITECTURE.md "Database Additions" section.

Create these tables:

1. tutor_sessions — tracks each tutor session
   - id (TEXT PRIMARY KEY)
   - user_id (TEXT NOT NULL)
   - started_at (TEXT NOT NULL)
   - ended_at (TEXT)
   - planner_model (TEXT)
   - session_summary (TEXT) — brief summary written by planner at end

2. tutor_activities — each activity within a session
   - id (TEXT PRIMARY KEY)
   - session_id (TEXT, FK to tutor_sessions)
   - activity_type (TEXT NOT NULL) — conversation, drill, mcq, etc.
   - tool_params_json (TEXT) — what the planner requested
   - result_json (TEXT) — what happened (scores, errors, etc.)
   - started_at (TEXT NOT NULL)
   - completed_at (TEXT)
   - score (REAL) — 0.0 to 1.0
   - concept_id (TEXT)

3. planner_decisions — every planner call logged for debugging
   - id (TEXT PRIMARY KEY)
   - session_id (TEXT, FK to tutor_sessions)
   - context_summary (TEXT) — abbreviated version of what planner saw
   - reasoning (TEXT) — planner's explanation
   - tool_name (TEXT)
   - tool_params_json (TEXT)
   - created_at (TEXT NOT NULL)

Add the CREATE TABLE statements to the ensure_tables() function.
Add helper functions: create_tutor_session(), record_tutor_activity(),
log_planner_decision(), get_tutor_session(), end_tutor_session().

Use UUIDs for IDs (import uuid, str(uuid.uuid4())).
```

---

## Prompt 6: Wire It All Together

```
Connect everything and make the tutor actually work end-to-end.

The flow should be:
1. User hits /tutor → sees chat UI
2. Page loads → auto-calls /tutor/start
3. Server creates TutorSession, reads memory files, calls planner
4. Planner calls propose_session_plan → tutor message appears in chat
5. User responds → /tutor/respond
6. Planner decides first activity (e.g., start_conversation)
7. Conversation card appears inline in chat
8. User chats for 4 turns via /tutor/conversation/respond
9. Conversation completes → /tutor/conversation/complete
10. Server evaluates, feeds to planner
11. Planner gives feedback + picks next activity
12. Loop until end_session

Test with:
- A brand new user (no memory files — should create defaults)
- The opening check-in flow
- A conversation activity
- A conjugation drill
- Transition between activities
- Session end with journal update

Make sure:
- The planner model is configurable in prompts.yaml
- Worker briefings are injected into conversation prompts
- Memory files are created for new learners
- Session journal gets updated at session end
- All planner decisions are logged to the database
- Error handling: if planner call fails, show a friendly message
  and offer to retry

Run the app with `python -m spanish_vibes` and verify /tutor works.
Fix any import errors, missing templates, or routing issues.
```

---

## Prompt 7: Conjugation Drill Polish

```
Polish the conjugation drill experience.

Currently the drill is basic. Make it feel good:

1. Accent-insensitive matching: "fui" matches "fui", "tuve" matches
   "tuvé" if the learner adds an incorrect accent (still mark as
   needing practice but count as correct).

2. Immediate visual feedback: correct → green flash + checkmark,
   wrong → red flash + show correct answer for 1.5 seconds, then
   auto-advance.

3. Progress bar at the top of the drill card.

4. Response time tracking: record ms per answer. The planner can
   use this to assess automaticity — getting it right in 2 seconds
   is different from getting it right in 10 seconds.

5. At drill completion, show a mini-summary: "6/8 correct, avg 3.2s.
   Missed: yo/tener (you said 'teno'), ellos/poder (you said 'podieron')."

6. Add more verbs to data/verb_conjugations.yaml:
   Present tense forms for: hablar, comer, vivir, ser, estar, ir,
   tener, querer, poder, hacer, decir, venir, poner, saber, dar.
   Preterite forms for all of the above.
   Imperfect forms for: ser, ir, hablar, comer, vivir, tener.

Style the drill to match the existing app's dark theme (bg-[#1a2d35],
slate borders, amber accents).
```

---

## Prompt 8: Translation Challenge Tool

```
Add the show_translation_challenge tool.

Read docs/AGENT_ARCHITECTURE.md Tool 4 definition.

1. Add the tool schema to tutor_agent.py's tool definitions.

2. Implement in tutor_tools.py:
   - Takes a list of English sentences + target grammar + difficulty
   - Renders a card showing one sentence at a time
   - Learner types their Spanish translation
   - Worker model (GPT-4o-mini) evaluates: grammar, vocabulary,
     communication success
   - Show corrections inline (reuse the correction chip pattern
     from conversation.py's _explode_corrections)
   - After all sentences, summarize results

3. Create template: templates/partials/tutor_activity_translation.html
   - Shows English sentence prominently
   - Optional hints (toggleable, hidden by default)
   - Text input for Spanish translation
   - Submit button
   - Feedback area below

4. Add routes:
   POST /tutor/translation/answer — evaluate one sentence
   POST /tutor/translation/complete — all sentences done

5. The evaluation prompt for the worker should focus on communication
   success, not just grammar. "Did they get the meaning across?" is
   more important than "is every article correct?"

   Include the worker_briefing in the evaluation prompt so the worker
   knows what specific grammar to watch for.
```

---

## Prompt 9: Circumlocution Challenge Tool

```
Add the show_circumlocution_challenge tool — the "express a complex
idea with simple vocabulary" exercise.

Read docs/AGENT_ARCHITECTURE.md Tool 11 definition.

This is the most pedagogically interesting tool. The learner gets a
complex English prompt and must express it in Spanish using whatever
vocabulary they have.

1. Add tool schema to tutor_agent.py.

2. Implement in tutor_tools.py:
   - Takes: English prompt, target grammar, vocab level, optional hints
   - Renders a card with the English prompt and a large text area
   - Worker evaluates on THREE dimensions:
     a) Communication success (0-1): Did they get the idea across?
     b) Grammar accuracy (0-1): How correct was the Spanish?
     c) Resourcefulness (0-1): Did they use creative workarounds?
        (e.g., "my boss was not good" instead of "my boss was demanding")
   - Feedback highlights both errors AND creative workarounds positively

3. Create template: tutor_activity_circumlocution.html
   - English prompt in a highlighted box
   - "Express this in Spanish using the words you know"
   - Optional hint chips (tap to reveal)
   - Large text area for the response
   - Submit button
   - Rich feedback card showing all three scores + specific highlights

4. The evaluation prompt is crucial. It should tell the worker:
   "The learner is A2 level and will NOT have advanced vocabulary.
   Evaluate primarily on whether the MEANING was communicated. Award
   high resourcefulness scores for creative workarounds. Examples:
   - 'mi jefe no fue bueno' for 'my boss was demanding' → good!
   - 'quise más dinero' for 'I wanted more money' → great!
   - 'mis amigos del trabajo viejo' for 'former colleagues' → creative!"
```

---

## Prompt 10: First Real Test Session

```
Run a complete end-to-end test of the tutor system.

1. Start the app: python -m spanish_vibes
2. Log in (or create a test user)
3. Navigate to /tutor
4. Go through a full session:
   - Opening check-in
   - At least one conversation with a persona
   - At least one conjugation drill
   - Session end with journal update

5. After the session, check:
   - data/learners/{user_id}/session_journal.md exists and has an entry
   - data/learners/{user_id}/grammar_notes.md exists
   - data/learners/{user_id}/learner_profile.md exists
   - The planner_decisions table has logged all decisions
   - The tutor_activities table has records for each activity

6. Fix anything that's broken. Common issues to watch for:
   - Planner returning malformed tool calls
   - HTMX swap targets not matching
   - Conversation state not persisting between turns
   - Memory files not being created for new learners
   - Worker briefing not being injected into conversation prompts

7. Start a SECOND session and verify:
   - The tutor references the previous session in its opening
   - The session journal now has 2 entries
   - Grammar notes reflect what was practiced

Report what worked and what needs fixing.
```
