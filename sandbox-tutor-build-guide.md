# Sandbox Tutor — Build Guide

Build a minimal Spanish tutor: one agent that chats, drops quiz cards, and remembers you between sessions.

---

## Step 1: Hello World FastAPI + HTMX

**Goal:** A page that sends a message and gets a response, all via HTMX. No LLM yet.

**Files to create:**
- `main.py` — FastAPI app with 2 routes
- `templates/index.html` — single page

**What to build:**
- `GET /` serves the page: a chat area (`<div id="chat">`) and an input form
- The form uses `hx-post="/chat"` with `hx-target="#chat"` and `hx-swap="beforeend"`
- `POST /chat` receives the message from the form, returns an HTML fragment like:
  ```html
  <div class="user-msg">You said: {message}</div>
  <div class="bot-msg">Echo: {message}</div>
  ```

**What you'll learn:** The HTMX swap model. The form posts, the server returns HTML, HTMX drops it into the chat div. This is the entire mental model — everything else is just making the server response smarter.

**Test it:** Type something, see it appear twice (your message + echo). Make sure the page doesn't reload.

---

## Step 2: Add OpenAI — The Simplest Agent

**Goal:** Replace the echo with an actual LLM response. Still no tools.

**What to change in `main.py`:**
- `pip install openai`
- Create an OpenAI client at module level
- Keep a conversation history in a global list (just for now — one user, in-memory)
- In `POST /chat`, append the user message to history, call `client.chat.completions.create()` with a system prompt like "You are a friendly Spanish tutor. Chat naturally. Keep responses short.", then append the assistant response to history
- Return the same HTML fragment but with the real LLM response

**Key decisions:**
- Use `gpt-4o-mini` — cheap, fast, good enough for chat
- Set `temperature=0.7` for natural conversation
- Keep `max_tokens` low (300) so responses stay concise
- The system prompt goes in messages[0], conversation history follows

**Important:** Make the route a regular `def`, NOT `async def`. The OpenAI SDK is synchronous — if you use `async def`, it blocks the event loop and the server freezes. FastAPI auto-runs `def` routes in a thread pool.

**Test it:** Have a short Spanish conversation. Verify the history works (it should remember what you said 2 messages ago).

---

## Step 3: Add One Tool — `create_quiz`

**Goal:** The LLM can now decide to either chat OR create a fill-in-the-blank quiz.

**What to add to `main.py`:**
- Define one tool schema (OpenAI function calling format):
  ```python
  tools = [{
      "type": "function",
      "function": {
          "name": "create_quiz",
          "description": "Create a fill-in-the-blank Spanish quiz when you want to test the learner.",
          "parameters": {
              "type": "object",
              "properties": {
                  "intro_message": {
                      "type": "string",
                      "description": "Brief message before the quiz (1 sentence)"
                  },
                  "sentences": {
                      "type": "array",
                      "items": {
                          "type": "object",
                          "properties": {
                              "text_with_blank": {"type": "string"},
                              "answer": {"type": "string"},
                              "hint": {"type": "string"}
                          },
                          "required": ["text_with_blank", "answer"]
                      },
                      "description": "2-4 fill-in-the-blank items"
                  }
              },
              "required": ["intro_message", "sentences"]
          }
      }
  }]
  ```
- Pass `tools=tools` to the `chat.completions.create()` call
- After the response, check: `if msg.tool_calls:` → the LLM wants to create a quiz. Otherwise it's a normal chat message.

**The agent loop (this is the core concept):**
```
User sends message
  → append to history
  → call LLM with history + tools
  → if response is text: return chat bubble HTML
  → if response is tool_call: parse the JSON args, render quiz HTML, return it
```

That's it. That's the whole agent loop. The LLM decides, you execute.

**What to add to `templates/index.html`:**
- Nothing changes on the page structure — the form still posts to `/chat`, HTMX still appends to `#chat`
- The server now sometimes returns a chat bubble, sometimes returns a quiz card. HTMX doesn't care — it just drops whatever HTML it gets.

**How to render the quiz card:**
- Return HTML directly from Python (f-string or a small Jinja template, your call)
- Each quiz item is a form with a text input and a hidden `answer` field
- The form posts to a new route: `POST /quiz/answer`

**Test it:** Chat normally for a bit, then say something like "test me on greetings." The LLM should call `create_quiz` and you should see quiz cards appear.

---

## Step 4: Handle Quiz Answers

**Goal:** User fills in the blank, submits, gets instant feedback.

**New route: `POST /quiz/answer`**
- Receives: `user_answer` and `correct_answer` from the form
- Compares them (lowercase, strip whitespace, ignore accents if you want to be nice)
- Returns an HTML fragment: green "✓ Correct!" or red "✗ The answer was: {correct}"
- Use `hx-target` on the quiz form to swap the form itself with the feedback

**Accent-tolerant comparison (optional but nice):**
```python
import unicodedata

def normalize(s):
    return unicodedata.normalize('NFD', s.lower().strip())
        .encode('ascii', 'ignore').decode('ascii')

correct = normalize(user_answer) == normalize(correct_answer)
```

**Key design point:** This is server-evaluated, no LLM call needed. The answers were set by the LLM when it created the quiz — now you just compare strings. Fast, cheap, deterministic.

**Test it:** Get a quiz, answer one right, answer one wrong. Verify the feedback swaps in correctly.

---

## Step 5: Wire the Quiz Result Back to the Agent

**Goal:** After the quiz, the agent knows how you did and responds accordingly.

**What to track:**
- After all quiz items are answered, collect the results (which ones right/wrong)
- Append a summary to the conversation history as a system or user message, something like: `"[Quiz result: 3/4 correct. Missed: 'tengo' (wrote 'tiene')]"`
- Call the LLM again — it now sees the quiz result in context and can react ("Nice work! Let's practice 'tener' a bit more...")

**How to trigger this:**
- After the last quiz item is answered, the feedback HTML includes a "Continue →" button
- That button posts to `POST /chat` with a hidden message like `"[quiz complete]"`
- The `/chat` handler sees the quiz results were just added to history and calls the LLM
- The LLM responds naturally based on the results

**Test it:** Complete a quiz, hit Continue, see the agent comment on your performance.

---

## Step 6: Memory — Survive a Server Restart

**Goal:** The agent remembers you between sessions. Kill the server, restart, and it knows your name and what you struggled with last time.

This is where you move from "chatbot" to "tutor." Without memory, every session starts from zero.

**The simplest approach — one markdown file per user:**

Create a `memory/` directory. For now you have one user, so one file: `memory/learner.md`

**What to store (start with just this):**
```markdown
# Learner Notes
Last session: 2026-02-19
Sessions completed: 3

## What I know about them
- Name: Artem
- Interested in travel
- Comfortable with present tense greetings

## Recent struggles
- Mixes up ser/estar
- Wrote "tiene" instead of "tengo" (yo form confusion)

## Next session idea
- Drill ser vs estar with location/description contrasts
```

**How to write it — add a second tool:**
```python
{
    "type": "function",
    "function": {
        "name": "save_notes",
        "description": "Save or update your notes about this learner. Call at the end of each session.",
        "parameters": {
            "type": "object",
            "properties": {
                "notes": {
                    "type": "string",
                    "description": "Full markdown notes. Include: what you know about them, recent struggles with specific examples, and your plan for next session."
                }
            },
            "required": ["notes"]
        }
    }
}
```

**How it fits into the agent loop:**
```
POST /chat receives "bye" or "I'm done"
  → LLM sees quit signal
  → LLM calls save_notes with updated markdown
  → You write the markdown to disk
  → Return a farewell message
```

**How to read it — inject into the system prompt:**
```python
def build_system_prompt():
    notes = ""
    if Path("memory/learner.md").exists():
        notes = Path("memory/learner.md").read_text()
    return f"""You are a friendly Spanish tutor.

Here are your notes about this learner from previous sessions:
---
{notes}
---

Use these notes to personalize the session. Reference specific things
they struggled with. Don't repeat activities they've already mastered.
If notes are empty, this is a new learner — introduce yourself and
start with basics."""
```

**The key insight:** The LLM writes its own memory. You don't decide what's worth remembering — the agent does, because it has the context of what happened. You just give it a tool to save and a place to read.

**What to change:**
- Read `memory/learner.md` at the start of each `/chat` call and put it in the system prompt
- Add `save_notes` to your tools list
- When the LLM calls `save_notes`, write the content to `memory/learner.md`
- After writing, return a confirmation message and the farewell

**Test it:**
1. Chat for a bit, make some mistakes, say "bye"
2. Check `memory/learner.md` — the LLM should have written useful notes
3. Kill the server, restart it
4. Start chatting again — the agent should reference your previous session

---

## Step 7: Memory That Doesn't Bloat

**Goal:** Handle the fact that one big markdown file will eventually get too long for the context window.

Step 6 works fine for 5-10 sessions. But the LLM rewrites the entire file every time, and eventually it'll either get too long or start dropping details. Fix this now before it becomes a problem.

**Split into two files:**

`memory/profile.md` — who they are (rarely changes):
```markdown
# Learner Profile
- Name: Artem
- Level: A2-ish
- Interests: travel, food, music
- Learning style: prefers drills before conversation
- Goals: conversational Spanish for travel
```

`memory/journal.md` — what happened (append-only):
```markdown
## 2026-02-19 — Session 3
- Focus: ser vs estar
- Quiz: 3/4 correct (missed estar for location)
- Conversation: good use of present tense greetings
- Note: gets confused when estar is used for temporary states vs locations
- Next: more estar practice, introduce "¿dónde está...?" pattern

## 2026-02-18 — Session 2
- Focus: present tense basics
- Quiz: 4/4 correct
- Conversation: hesitant but accurate
- Next: try ser vs estar
```

**Two tools instead of one:**
- `update_profile` — rewrites `profile.md` (call when you learn something new about the learner)
- `add_journal_entry` — appends to `journal.md` (call at end of every session)

**Reading with a window:**
When building the system prompt, read the full profile but only the last 3-5 journal entries. This keeps context usage bounded:

```python
def read_journal(last_n=5):
    text = Path("memory/journal.md").read_text()
    # Split on "## 20" headings, take last N
    entries = text.split("\n## 20")
    recent = entries[-last_n:]
    return "\n## 20".join(recent)
```

**Test it:**
1. Run 3-4 sessions, ending each with "bye"
2. Check that `journal.md` has one entry per session
3. Check that `profile.md` evolves as the agent learns about you
4. Restart the server — the agent should reference specific past sessions

---

## Step 8: Polish

Once steps 1-7 work, make it feel good:

- **Loading indicator:** Add `hx-indicator` or toggle a spinner class during LLM calls
- **Disable button while waiting:** `hx-disabled-elt="find button"` on forms
- **Scroll to bottom:** A `scrollChat()` function called via `hx-on::after-request`
- **Styling:** Dark theme, rounded cards, simple CSS — keep it minimal
- **Error handling:** If the LLM call fails, return a friendly error HTML fragment instead of crashing

---

## Architecture Summary

```
Browser (HTMX)
  │
  ├── POST /chat        → LLM decides: chat bubble OR quiz card OR save memory
  ├── POST /quiz/answer → server-side string comparison, no LLM
  └── GET /             → serves the single page

main.py (~200-300 lines)
  ├── OpenAI client + conversation history (in-memory list)
  ├── Tool schemas: create_quiz, update_profile, add_journal_entry
  ├── Agent loop: call LLM → check for tool_calls → render HTML or write memory
  ├── Quiz evaluation: string comparison, no LLM needed
  └── Memory: read markdown into system prompt, write via tool calls

memory/
  ├── profile.md    — who the learner is (overwritten by LLM)
  └── journal.md    — session log (appended by LLM)

templates/index.html (one file)
  ├── Chat container
  ├── Input form
  └── CSS (inline or <style> block)
```

Total: 2-3 files of code, 2 markdown files for memory. The entire thing fits in your head.

---

## What You're Practising

- **Step 1-2:** The HTMX swap model + basic LLM integration
- **Step 3:** Tool calling — the LLM decides what to do, not the user
- **Step 4:** Server-side evaluation — not everything needs an LLM
- **Step 5:** The feedback loop — results go back to the agent
- **Step 6:** Memory — the agent writes its own notes, you inject them into context
- **Step 7:** Memory management — keeping context bounded as sessions accumulate
- **Step 8:** Polish — making it feel responsive

Once this feels solid, you can layer on: multiple activity types, richer evaluation, concept tracking, multi-user support — but only when you understand each piece.
