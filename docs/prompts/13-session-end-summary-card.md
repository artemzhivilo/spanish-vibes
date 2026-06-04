# Prompt 13: Session-End Summary Card

```
When the tutor calls end_session, the session currently just stops without
a proper wrap-up. Build a session-end summary card that gives the learner
a clear sense of accomplishment and direction.

### 1. Update the end_session tool implementation in tutor_tools.py

The planner already passes structured fields when calling end_session
(see the END SESSION OUTPUT FORMAT section in the planner system prompt
in tutor_agent.py). Render these into a polished card:

Create templates/partials/tutor_session_end.html:

```html
<!-- Session end summary card -->
<div class="session-end-card bg-gradient-to-br from-[#1a2d35] to-[#0f1f26]
            rounded-2xl border border-slate-600/40 p-6 max-w-lg mx-auto my-6">

  <!-- Header with session number -->
  <div class="text-center mb-4">
    <span class="text-3xl">🎉</span>
    <h2 class="text-xl font-bold text-white mt-2">Session Complete!</h2>
    {% if session_number %}
    <p class="text-slate-400 text-sm">Session #{{ session_number }}</p>
    {% endif %}
  </div>

  <!-- Summary message from tutor -->
  <p class="text-slate-200 text-center mb-5">{{ summary_message }}</p>

  <!-- Activities completed -->
  {% if activities_summary %}
  <div class="mb-4">
    <h3 class="text-sm font-semibold text-slate-400 uppercase tracking-wider mb-2">Activities</h3>
    {% for activity in activities_summary %}
    <div class="flex items-center justify-between py-1.5 border-b border-slate-700/50 last:border-0">
      <span class="text-slate-300">{{ activity.type }}</span>
      {% if activity.score is not none %}
      <span class="text-amber-400 font-mono text-sm">{{ (activity.score * 100)|int }}%</span>
      {% endif %}
      {% if activity.highlight %}
      <span class="text-slate-400 text-xs ml-2">{{ activity.highlight }}</span>
      {% endif %}
    </div>
    {% endfor %}
  </div>
  {% endif %}

  <!-- Breakthroughs -->
  {% if breakthroughs %}
  <div class="mb-4 bg-emerald-900/20 rounded-lg p-3 border border-emerald-700/30">
    <h3 class="text-sm font-semibold text-emerald-400 mb-1">💪 Breakthroughs</h3>
    {% for item in breakthroughs %}
    <p class="text-slate-300 text-sm">• {{ item }}</p>
    {% endfor %}
  </div>
  {% endif %}

  <!-- Still working on -->
  {% if still_working_on %}
  <div class="mb-4 bg-amber-900/20 rounded-lg p-3 border border-amber-700/30">
    <h3 class="text-sm font-semibold text-amber-400 mb-1">🎯 Keep Practicing</h3>
    {% for item in still_working_on %}
    <p class="text-slate-300 text-sm">• {{ item }}</p>
    {% endfor %}
  </div>
  {% endif %}

  <!-- Next session preview -->
  {% if next_session_preview %}
  <p class="text-slate-400 text-sm text-center mt-4 italic">
    Next time: {{ next_session_preview }}
  </p>
  {% endif %}

  <!-- Start new session button -->
  <div class="text-center mt-6">
    <button hx-post="/tutor/new-session"
            hx-target="#tutor-chat"
            hx-swap="innerHTML"
            class="px-6 py-3 bg-violet-600 hover:bg-violet-500 text-white
                   font-semibold rounded-xl transition-colors">
      Start New Session →
    </button>
  </div>
</div>
```

### 2. Update the tool_end_session function in tutor_tools.py

Parse the planner's params and render the template above. Handle missing
optional fields gracefully (some fields may be absent):
- summary_message (required) — the tutor's closing words
- activities_summary (optional) — list of {type, score, highlight}
- breakthroughs (optional) — list of strings
- still_working_on (optional) — list of strings
- next_session_preview (optional) — string
- session_number (optional) — integer

### 3. After end_session, trigger memory updates

The planner should call update_session_journal and update_grammar_notes
AFTER end_session. This is already in the planner system prompt. But make
sure the route handler in tutor_routes.py continues processing planner
tool calls after end_session renders — don't stop the loop early. The
_drain_memory_tools_after_end function (if it exists) should handle this.

### 4. The /tutor/new-session endpoint

If it already exists, verify it works. If not, create it:
- POST /tutor/new-session
- Creates a fresh TutorSession (new session_id)
- Calls plan_next_action() for the opening
- Returns the full chat area HTML (clears old messages, shows new opening)

Test: complete a full session and verify the summary card renders with
scores, breakthroughs, and a working "Start New Session" button.
```
