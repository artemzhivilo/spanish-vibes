"""Tool implementations for the agent-based tutor.

Each tool corresponds to one of the planner's function call options.
A tool receives the planner's params + the TutorSession, executes the
activity (possibly calling Tier 2 LLM workers), and returns a ToolResult.

ToolResult.html      → HTMX partial sent to the browser
ToolResult.result_summary → what the planner sees at the next turn
ToolResult.activity_data  → raw data for the DB record
"""

from __future__ import annotations

import html
import json
import random
import re
import time as _time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape

from .conversation import ConversationCard, ConversationEngine, ConversationMessage
from .flow_ai import _get_client, ai_available
from .personas import load_persona
from .template_helpers import make_words_tappable, register_template_filters
from .tutor_agent import TutorSession, TutorActivityResult


# ── Paths ─────────────────────────────────────────────────────────────────────

_PACKAGE_ROOT = Path(__file__).resolve().parent
_PROJECT_ROOT = _PACKAGE_ROOT.parent.parent
_CONJ_TABLE_PATH = _PROJECT_ROOT / "data" / "verb_conjugations.yaml"
_TEMPLATES_DIR = _PROJECT_ROOT / "templates"

# ── Jinja2 env for partial templates ──────────────────────────────────────────

_jinja = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=select_autoescape(["html"]),
    trim_blocks=True,
    lstrip_blocks=True,
)
register_template_filters(_jinja)


def _render(template_name: str, **ctx: Any) -> str:
    return _jinja.get_template(template_name).render(**ctx)


_CONJ_TABLE: dict[str, Any] | None = None


def _load_conj_table() -> dict[str, Any]:
    global _CONJ_TABLE
    if _CONJ_TABLE is None:
        try:
            _CONJ_TABLE = (
                yaml.safe_load(_CONJ_TABLE_PATH.read_text(encoding="utf-8")) or {}
            )
        except Exception:
            _CONJ_TABLE = {}
    return _CONJ_TABLE


# ── ToolResult ────────────────────────────────────────────────────────────────


@dataclass
class ToolResult:
    """What a tool execution returns."""

    html: str  # HTMX partial to append to #tutor-chat
    result_summary: str  # human-readable for planner next turn
    activity_data: dict[str, Any] = field(default_factory=dict)
    activity_result: TutorActivityResult | None = None  # if an activity completed


# ── Normalisation helpers ─────────────────────────────────────────────────────


def _normalize(text: str) -> str:
    """Lowercase, strip accents and punctuation for loose comparison."""
    nfkd = unicodedata.normalize("NFKD", text.casefold().strip())
    return "".join(c for c in nfkd if not unicodedata.combining(c)).strip()


def _check_conjugation(user_answer: str, correct: str) -> tuple[bool, bool]:
    """
    Return (is_correct, accent_only).

    is_correct  — normalized forms match (accent-insensitive).
    accent_only — True when is_correct but the raw forms differ (accent slip).
    """
    user_norm = _normalize(user_answer)
    correct_norm = _normalize(correct)
    is_correct = user_norm == correct_norm
    accent_only = (
        is_correct
        and user_answer.strip().lower() != correct.strip().lower()
        and bool(user_answer.strip())
    )
    return is_correct, accent_only


def _sanitize_conversation_topic(raw_topic: str) -> str:
    """Normalize planner topic text into a learner-facing Spanish topic."""
    topic = (raw_topic or "").strip()
    if not topic:
        return "presentaciones"

    lowered = topic.casefold()

    # Detect intro/greeting topics and keep them simple
    intro_markers = (
        "introductions",
        "introduction",
        "greetings",
        "greeting",
        "where you're from",
        "where you live",
        "your name",
        "getting to know",
        "basics",
        "intro",
    )
    if any(marker in lowered for marker in intro_markers):
        return "presentaciones"

    instruction_markers = (
        "day to day",
        "daily life",
        "name",
    )
    if ":" in topic and any(marker in lowered for marker in instruction_markers):
        return "tu día"

    english_heavy = bool(
        re.search(r"\b(the|and|with|what|where|your|you|from|about|name)\b", lowered)
    )
    if english_heavy and len(topic) > 36:
        return "tu día"

    return topic


# ── Tool: propose_session_plan ────────────────────────────────────────────────


def tool_propose_session_plan(
    params: dict[str, Any], session: TutorSession
) -> ToolResult:
    """Render the planner's opening check-in as a tutor chat bubble."""
    tutor_message = params.get("tutor_message", "¡Hola! Let's get started.")
    focus = params.get("focus_concepts", [])
    goal = params.get("session_goal", "")
    activities = params.get("suggested_activities", [])
    duration = params.get("estimated_duration_min", 20)

    focus_str = ", ".join(focus) if focus else "general practice"
    plan_preview = " → ".join(activities) if activities else ""

    html = _render(
        "partials/tutor_message.html",
        message=tutor_message,
        plan_preview=plan_preview,
        duration_min=duration,
        show_input=True,
        session_id=session.session_id,
        is_feedback=False,
        show_stats=False,
        stats={},
        input_placeholder="Sounds good! / Actually, I'd prefer...",
    )

    summary = (
        f"Session plan proposed. Focus: {focus_str}. Goal: {goal}. "
        f"Waiting for learner's response."
    )

    return ToolResult(
        html=html,
        result_summary=summary,
        activity_data={"focus_concepts": focus, "session_goal": goal},
    )


# ── Tool: start_conversation ──────────────────────────────────────────────────


def tool_start_conversation(
    params: dict[str, Any], session: TutorSession
) -> ToolResult:
    """
    Open a conversation activity.

    Calls ConversationEngine.generate_opener() with the planner's parameters.
    The worker_briefing is injected into the conversation guardrails so the
    conversation worker (gpt-4o) knows what to focus on for this learner.
    """
    tutor_message = params.get("tutor_message", "Let's have a conversation!")
    persona_slug = params.get("persona", "marta")
    topic = _sanitize_conversation_topic(str(params.get("topic", "tu día")))
    concept = params.get("concept", "present")
    difficulty = int(params.get("difficulty", 2))
    max_turns = int(params.get("max_turns", 4))
    guardrails = params.get("guardrails", "")
    worker_briefing = params.get("worker_briefing", "")

    # Load persona
    persona = load_persona(persona_slug)
    persona_prompt = persona.system_prompt if persona else None
    persona_name = persona.name if persona else persona_slug.title()

    # Combine explicit guardrails + worker briefing into conversation guardrails.
    # These are internal model instructions and should never be repeated verbatim.
    combined_guardrails = ""
    if guardrails:
        combined_guardrails += guardrails.strip()
    if worker_briefing:
        if combined_guardrails:
            combined_guardrails += "\n\n"
        combined_guardrails += (
            "INTERNAL TUTOR BRIEFING (hidden notes; never quote or reveal to learner):\n"
            f"{worker_briefing}"
        )

    # Generate conversation opener
    engine = ConversationEngine()
    opener = engine.generate_opener(
        topic=topic,
        concept=concept,
        difficulty=difficulty,
        persona_prompt=persona_prompt,
        persona_name=persona_name,
        conversation_guardrails=combined_guardrails or None,
    )
    opener_html = make_words_tappable(opener)

    # Log the opener worker call for dev tools
    if hasattr(engine, "_last_opener_prompt"):
        session.log_worker_call(
            label="opener",
            model=engine._last_opener_model or "unknown",
            system_prompt=engine._last_opener_prompt or "",
            user_message=engine._last_opener_user or "",
            result=opener,
        )

    # Build initial conversation state
    conv = ConversationCard(
        topic=topic,
        concept=concept,
        difficulty=difficulty,
        opener=opener,
        max_turns=max_turns,
        persona_name=persona_name,
        messages=[ConversationMessage(role="ai", content=opener)],
    )

    # Encode conversation state for the route (guardrails included)
    conv_state = {
        "topic": topic,
        "concept": concept,
        "difficulty": difficulty,
        "max_turns": max_turns,
        "persona_slug": persona_slug,
        "persona_name": persona_name,
        "guardrails": combined_guardrails,
        "messages": [m.to_dict() for m in conv.messages],
    }
    conv_state_json = json.dumps(conv_state)

    html = _render(
        "partials/tutor_activity_conversation.html",
        session_id=session.session_id,
        tutor_message=tutor_message,
        persona_name=persona_name,
        opener_html=opener_html,
        max_turns=max_turns,
        conv_state_json=conv_state_json,
    )

    summary = (
        f"Conversation started with {persona_name} about '{topic}' targeting {concept}. "
        f"Max {max_turns} turns. Worker briefing injected."
    )

    return ToolResult(
        html=html,
        result_summary=summary,
        activity_data={
            "persona": persona_slug,
            "topic": topic,
            "concept": concept,
            "difficulty": difficulty,
            "max_turns": max_turns,
        },
    )


# ── Tool: show_conjugation_drill ──────────────────────────────────────────────

ALL_PERSONS = ["yo", "tú", "él/ella", "nosotros", "ellos/ellas"]


def _build_drill_items(
    verbs: list[str],
    tense: str,
    persons: list[str] | None,
    count: int,
) -> list[dict[str, str]]:
    """
    Generate drill items from the YAML conjugation table.
    Returns list of {person, verb, tense} dicts — no correct answer embedded
    so future answers are not exposed in the form HTML.
    """
    table = _load_conj_table()
    tense_data = table.get(tense, {})
    target_persons = persons if persons else ALL_PERSONS

    items: list[dict[str, str]] = []
    for verb in verbs:
        verb_data = tense_data.get(verb, {})
        for person in target_persons:
            correct = verb_data.get(person)
            if correct:
                items.append({"person": person, "verb": verb, "tense": tense})

    if not items:
        return []

    random.shuffle(items)
    return items[:count]


def tool_show_conjugation_drill(
    params: dict[str, Any], session: TutorSession
) -> ToolResult:
    """Build and render a conjugation drill card."""
    tutor_message = params.get("tutor_message", "Quick drill — type the correct form.")
    verbs = params.get("verbs", ["tener", "ir", "hacer"])
    tense = params.get("tense", "preterite")
    persons = params.get("persons")  # None = all persons
    count = min(int(params.get("count", 6)), 12)

    items = _build_drill_items(verbs, tense, persons, count)

    if not items:
        # Verb/tense not in our table — graceful fallback
        fallback_msg = (
            f"{tutor_message} "
            f"(Drill unavailable for {tense}/{', '.join(verbs)} — let's move on.)"
        )
        return ToolResult(
            html=_render(
                "partials/tutor_message.html",
                message=fallback_msg,
                is_feedback=False,
                show_stats=False,
                stats={},
                show_input=False,
                plan_preview="",
                session_id=session.session_id,
            ),
            result_summary=f"Drill unavailable: {tense}/{verbs} not in conjugation table.",
        )

    items_json = json.dumps(items)
    first = items[0]

    tense_label = tense.replace("_", " ").title()

    html = _render(
        "partials/tutor_activity_drill.html",
        session_id=session.session_id,
        tutor_message=tutor_message,
        tense_label=tense_label,
        items_json=items_json,
        first_person=first["person"],
        first_verb=first["verb"],
        total=len(items),
    )

    summary = (
        f"Conjugation drill started: {tense} of {', '.join(verbs)}. {len(items)} items."
    )

    return ToolResult(
        html=html,
        result_summary=summary,
        activity_data={
            "verbs": verbs,
            "tense": tense,
            "items": items,
        },
    )


def render_drill_answer(
    items: list[dict[str, str]],
    current_index: int,
    correct_count: int,
    errors: list[str],
    user_answer: str,
    session_id: str,
    item_started_at: int = 0,
    response_times_json: str = "[]",
) -> tuple[str, bool]:
    """
    Process one drill answer and render the next item (or completion card).
    Returns (html, drill_complete).
    """
    item = items[current_index]
    # Look up correct form server-side (not embedded in form to avoid answer leakage)
    table = _load_conj_table()
    correct_form = (
        table.get(item["tense"], {}).get(item["verb"], {}).get(item["person"], "")
    )
    is_correct, accent_only = _check_conjugation(user_answer, correct_form)
    new_correct = correct_count + (1 if is_correct else 0)

    # Track response time
    elapsed_ms = (
        int(_time.time() * 1000) - item_started_at if item_started_at > 0 else 0
    )

    # Accumulate timing data
    response_times: list[dict] = json.loads(response_times_json or "[]")
    response_times.append(
        {
            "person": item["person"],
            "verb": item["verb"],
            "time_ms": elapsed_ms,
            "correct": is_correct,
            "accent_only": accent_only,
            "user_answer": user_answer,
            "correct_form": correct_form,
        }
    )
    new_response_times_json = json.dumps(response_times)

    # Build error list
    new_errors = list(errors)
    if not is_correct:
        new_errors.append(
            f"{item['verb']}({item['person']}): said '{user_answer}' → {correct_form}"
        )
    elif accent_only:
        new_errors.append(
            f"{item['verb']}({item['person']}): accent slip '{user_answer}' → {correct_form} (counted correct)"
        )

    next_index = current_index + 1
    total = len(items)

    if next_index >= total:
        # ── Completion card ──────────────────────────────────────────────────
        score_pct = int(new_correct / total * 100)
        praise = (
            "¡Excelente!"
            if score_pct >= 80
            else "¡Buen intento!"
            if score_pct >= 60
            else "Keep practising!"
        )

        timed = [r for r in response_times if r["time_ms"] > 0]
        avg_ms = sum(r["time_ms"] for r in timed) / max(1, len(timed)) if timed else 0
        avg_s = avg_ms / 1000

        true_errors = [r for r in response_times if not r["correct"]]
        accent_slips = [r for r in response_times if r.get("accent_only")]

        # Missed section (true errors only)
        missed_html = ""
        if true_errors:
            rows = "".join(
                f"<li>"
                f'<span class="drill-err-person">{r["person"]}</span>'
                f" / "
                f'<span class="drill-err-verb">{r["verb"]}</span>'
                f' — you said "<span class="drill-err-user">{r["user_answer"]}</span>",'
                f" correct: <strong>{r['correct_form']}</strong>"
                f"</li>"
                for r in true_errors
            )
            missed_html = (
                '<div class="drill-missed">'
                '<p class="drill-missed-label">Missed:</p>'
                f'<ul class="drill-errors">{rows}</ul>'
                "</div>"
            )

        # Accent slips section
        slips_html = ""
        if accent_slips:
            rows = "".join(
                f"<li>{r['verb']}({r['person']}): you typed &ldquo;{r['user_answer']}&rdquo;,"
                f" correct form: {r['correct_form']}</li>"
                for r in accent_slips
            )
            slips_html = (
                '<div class="drill-accent-slips">'
                '<p class="drill-missed-label" style="color:#94a3b8">Accent slips (counted correct):</p>'
                f'<ul class="drill-errors" style="color:#94a3b8">{rows}</ul>'
                "</div>"
            )

        html = f"""\
<div class="tutor-activity-card" id="activity-drill">
  <div class="activity-header">
    <span class="drill-badge">⚡ Drill complete</span>
    <span class="drill-progress">{new_correct} / {total}</span>
  </div>
  <div class="drill-complete">
    <p class="drill-score">{score_pct}%</p>
    <p class="drill-score-label">{praise} · avg {avg_s:.1f}s per answer</p>
    {missed_html}
    {slips_html}
  </div>
  <form hx-post="/tutor/drill/complete"
        hx-target="#tutor-chat"
        hx-swap="beforeend"
        hx-on::after-request="scrollChat()"
        class="drill-done-form">
    <input type="hidden" name="session_id" value="{session_id}">
    <input type="hidden" name="score" value="{new_correct / total:.3f}">
    <input type="hidden" name="errors_json" value="{_escape_attr(json.dumps(new_errors))}">
    <input type="hidden" name="total" value="{total}">
    <input type="hidden" name="response_times_json" value="{_escape_attr(new_response_times_json)}">
    <button type="submit" class="drill-continue-btn">Continue →</button>
  </form>
</div>"""
        return html, True

    # ── Mid-drill card ───────────────────────────────────────────────────────
    next_item = items[next_index]
    pct = next_index / total * 100

    # Feedback block for the answer just given
    if is_correct and not accent_only:
        fb_class = "drill-feedback-block drill-feedback-correct"
        time_note = ""
        if elapsed_ms > 0:
            elapsed_s = elapsed_ms / 1000
            if elapsed_s > 8:
                time_note = f'<span class="drill-feedback-time">{elapsed_s:.1f}s — keep practising for speed</span>'
            elif elapsed_s < 3:
                time_note = (
                    f'<span class="drill-feedback-time">{elapsed_s:.1f}s ⚡</span>'
                )
        fb_content = f"✓ {correct_form}{time_note}"
    elif accent_only:
        fb_class = "drill-feedback-block drill-feedback-accent"
        fb_content = f"≈ Check accent: {correct_form}"
    else:
        fb_class = "drill-feedback-block drill-feedback-wrong"
        fb_content = f"✗ Correct: {correct_form}"

    items_json_str = json.dumps(items)

    # For wrong answers the input is disabled until JS re-enables it after 1500ms
    input_disabled = " disabled" if not is_correct and not accent_only else ""
    activate_js = (
        "setTimeout(activate, 1500);"
        if not is_correct and not accent_only
        else "activate();"
    )

    html = f"""\
<div class="tutor-activity-card" id="activity-drill">
  <div class="drill-progress-bar"><div class="drill-progress-bar-fill" style="width:{pct:.1f}%"></div></div>
  <div class="activity-header">
    <span class="drill-badge">⚡ Drill</span>
    <span class="drill-progress" id="drill-progress">{next_index + 1} / {total}</span>
  </div>
  <div class="drill-item" id="drill-item">
    <div class="{fb_class}">{fb_content}</div>
    <p class="drill-prompt">
      <span class="drill-person">{next_item["person"]}</span>
      <span class="drill-slash">/</span>
      <span class="drill-verb">{next_item["verb"]}</span>
      <span class="drill-arrow">→</span>
    </p>
  </div>
  <form hx-post="/tutor/drill/answer"
        hx-target="#activity-drill"
        hx-swap="outerHTML"
        class="drill-input-form"
        id="drill-form">
    <input type="hidden" name="session_id" value="{session_id}">
    <input type="hidden" name="items_json" value="{_escape_attr(items_json_str)}">
    <input type="hidden" name="current_index" value="{next_index}">
    <input type="hidden" name="correct_count" value="{new_correct}">
    <input type="hidden" name="errors_json" value="{_escape_attr(json.dumps(new_errors))}">
    <input type="hidden" name="item_started_at" value="" id="drill-timer">
    <input type="hidden" name="response_times_json" value="{_escape_attr(new_response_times_json)}">
    <input type="text"
           name="user_answer"
           placeholder="Type the conjugation..."
           class="drill-input"
           autocomplete="off"
           autocorrect="off"
           autocapitalize="off"
           spellcheck="false"{input_disabled}>
    <button type="submit" class="drill-submit-btn">Check →</button>
  </form>
</div>
<script>
(function() {{
  var inp = document.querySelector('#activity-drill .drill-input');
  var timer = document.getElementById('drill-timer');
  function activate() {{
    if (inp) {{ inp.disabled = false; inp.focus(); }}
    if (timer) timer.value = Date.now();
  }}
  {activate_js}
}})();
</script>"""
    return html, False


# ── Tool: give_feedback ───────────────────────────────────────────────────────


def tool_give_feedback(params: dict[str, Any], session: TutorSession) -> ToolResult:
    """Render the planner's feedback message as a tutor chat bubble."""
    message = params.get("message", "Good work!")
    show_stats = params.get("show_stats", False)
    stats = params.get("stats", {})

    html = _render(
        "partials/tutor_message.html",
        message=message,
        is_feedback=True,
        show_stats=show_stats,
        stats=stats,
        show_input=True,
        plan_preview="",
        session_id=session.session_id,
        input_placeholder="Continue →",
    )

    return ToolResult(
        html=html,
        result_summary=f"Feedback given: {message[:80]}",
        activity_data={"message": message, "stats": stats},
    )


# ── Tool: end_session ─────────────────────────────────────────────────────────


def tool_end_session(params: dict[str, Any], session: TutorSession) -> ToolResult:
    """Render the session wrap-up card."""
    summary = str(params.get("summary_message", "Great session!"))
    activities_summary = params.get("activities_summary", [])
    breakthroughs = params.get("breakthroughs", [])
    still_working_on = params.get("still_working_on", [])
    next_session_preview = str(params.get("next_session_preview", "")).strip()
    session_number = params.get("session_number")

    if not isinstance(activities_summary, list):
        activities_summary = []
    if not isinstance(breakthroughs, list):
        breakthroughs = [str(breakthroughs)]
    if not isinstance(still_working_on, list):
        still_working_on = [str(still_working_on)]

    normalized_activities: list[dict[str, Any]] = []
    for raw in activities_summary:
        if not isinstance(raw, dict):
            continue
        raw_type = str(raw.get("type", "")).strip()
        if not raw_type:
            continue
        score = float(raw.get("score", 0.0) or 0.0)
        score = max(0.0, min(1.0, score))
        highlight = str(raw.get("highlight", "")).strip()
        normalized_activities.append(
            {
                "type": raw_type.replace("_", " ").title(),
                "score": score,
                "highlight": highlight,
            }
        )

    if not normalized_activities:
        for act in session.activities:
            normalized_activities.append(
                {
                    "type": act.activity_type.replace("_", " ").title(),
                    "score": max(0.0, min(1.0, float(act.score))),
                    "highlight": act.notes,
                }
            )

    total_acts = len(session.activities)
    avg_score = (
        sum(a.score for a in session.activities) / total_acts if total_acts > 0 else 0.0
    )

    html = _render(
        "partials/tutor_session_end.html",
        session_id=session.session_id,
        user_id=session.user_id,
        summary_message=summary,
        activities_summary=normalized_activities,
        breakthroughs=breakthroughs,
        still_working_on=still_working_on,
        next_session_preview=next_session_preview,
        session_number=session_number,
    )

    result = TutorActivityResult(
        activity_type="end_session",
        score=avg_score,
        errors=[],
        concepts_practiced=list(
            {c for a in session.activities for c in a.concepts_practiced}
        ),
        notes=summary[:200],
    )

    return ToolResult(
        html=html,
        result_summary=f"Session ended. Avg score: {avg_score:.0%}. Activities: {total_acts}.",
        activity_data={
            "activities_summary": normalized_activities,
            "breakthroughs": breakthroughs,
            "still_working_on": still_working_on,
            "next_session_preview": next_session_preview,
            "session_number": session_number,
        },
        activity_result=result,
    )


# ── Tool: update_session_journal ──────────────────────────────────────────────


def tool_update_session_journal(
    params: dict[str, Any], session: TutorSession
) -> ToolResult:
    """Append journal entry to learner's session_journal.md."""
    entry = params.get("entry", "")
    if entry:
        session.update_journal(entry)

    return ToolResult(
        html="",  # memory tools produce no HTML
        result_summary="Session journal updated.",
        activity_data={"entry_length": len(entry)},
    )


# ── Tool: update_grammar_notes ────────────────────────────────────────────────


def tool_update_grammar_notes(
    params: dict[str, Any], session: TutorSession
) -> ToolResult:
    """Update learner's grammar_notes.md for a specific concept."""
    concept = params.get("concept", "unknown")
    status = params.get("status")
    update = params.get("update", "")

    if concept and update:
        session.update_grammar_notes(concept=concept, status=status, update=update)

    return ToolResult(
        html="",
        result_summary=f"Grammar notes updated: {concept} → {status}",
        activity_data={"concept": concept, "status": status},
    )


# ── Tool: show_translation_challenge ─────────────────────────────────────────

_PROFICIENCY_LABEL = {1: "beginner", 2: "intermediate", 3: "upper-intermediate"}


def _evaluate_translation(
    english: str,
    spanish: str,
    target_grammar: str,
    difficulty: int,
    worker_briefing: str,
) -> dict[str, Any]:
    """Call gpt-4o-mini to evaluate a Spanish translation for communication success."""
    if not ai_available():
        return _translation_fallback()

    client = _get_client()
    if client is None:
        return _translation_fallback()

    level_label = _PROFICIENCY_LABEL.get(difficulty, "intermediate")
    system = f"""\
You are an expert Spanish language evaluator for {level_label} learners.

EVALUATION PHILOSOPHY:
- Communication success is MOST IMPORTANT. Did the learner convey the meaning?
- Grammar accuracy matters but is secondary to communication.
- A learner who says "mi jefe no fue bueno" instead of "mi jefe fue exigente"
  has communicated successfully — that is the skill we want. Credit it.
- Be encouraging. Mention what worked before corrections.
- Max 3 corrections. Only flag genuine errors, not stylistic choices.

TARGET GRAMMAR: {target_grammar}

WORKER BRIEFING (from the session tutor):
{worker_briefing or "Evaluate grammar and communication at the learner's level."}

Respond ONLY with valid JSON in this exact format:
{{
  "communicated_successfully": true,
  "score": 0.85,
  "feedback": "1-2 sentences of encouraging, specific feedback",
  "corrections": [
    {{"original": "word/phrase they wrote", "corrected": "better form", "explanation": "brief reason"}}
  ]
}}

Score guide:
- 0.9-1.0: meaning clear, target grammar correct or nearly so
- 0.7-0.9: meaning clear, some grammar issues
- 0.5-0.7: meaning partially conveyed, significant errors
- <0.5: meaning unclear or pervasive errors"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": f"English: {english}\nSpanish: {spanish}"},
            ],
            temperature=0.2,
            max_tokens=400,
        )
        raw = (response.choices[0].message.content or "").strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        result: dict[str, Any] = json.loads(raw)
        result.setdefault("communicated_successfully", True)
        result.setdefault("score", 0.7)
        result.setdefault("feedback", "")
        result.setdefault("corrections", [])
        result["score"] = max(0.0, min(1.0, float(result["score"])))
        return result
    except Exception:
        return _translation_fallback()


def _translation_fallback() -> dict[str, Any]:
    return {
        "communicated_successfully": True,
        "score": 0.7,
        "feedback": "Nice try! (AI evaluation unavailable — keep practising.)",
        "corrections": [],
    }


def _build_error_list(
    sentences: list[str],
    all_corrections: list[list[dict[str, Any]]],
) -> list[str]:
    """Flatten per-sentence corrections into short error strings for the DB."""
    errors: list[str] = []
    for i, corrections in enumerate(all_corrections):
        prefix = sentences[i][:40] if i < len(sentences) else f"sentence {i + 1}"
        for c in corrections:
            errors.append(f"'{prefix}': {c.get('original')} → {c.get('corrected')}")
    return errors[:8]


def render_translation_answer(
    sentences: list[str],
    current_index: int,
    correct_count: int,
    scores: list[float],
    all_corrections: list[list[dict[str, Any]]],
    user_translation: str,
    session_id: str,
    target_grammar: str,
    difficulty: int,
    hints: list[str],
    worker_briefing: str,
) -> tuple[str, bool]:
    """
    Evaluate one translation and render the next sentence card or completion card.
    Returns (html, is_complete).
    """
    english = sentences[current_index]
    eval_result = _evaluate_translation(
        english=english,
        spanish=user_translation,
        target_grammar=target_grammar,
        difficulty=difficulty,
        worker_briefing=worker_briefing,
    )

    score = eval_result["score"]
    feedback = eval_result.get("feedback", "")
    corrections: list[dict[str, Any]] = eval_result.get("corrections", [])
    communicated = eval_result.get("communicated_successfully", True)

    new_scores = scores + [score]
    new_corrections = all_corrections + [corrections]
    new_correct = correct_count + (1 if communicated else 0)
    next_index = current_index + 1
    total = len(sentences)

    # Correction chips for this sentence
    chips_html = ""
    if corrections:
        chips = "".join(
            f'<span class="corr-chip" title="{_escape_attr(c.get("explanation", ""))}">'
            f"<del>{c.get('original', '')}</del> → {c.get('corrected', '')}</span>"
            for c in corrections
        )
        chips_html = f'<div class="correction-chips">{chips}</div>'

    # Feedback class for this answer
    if score >= 0.85:
        fb_class = "transl-feedback-block transl-feedback-correct"
        fb_icon = "✓"
    elif score >= 0.6:
        fb_class = "transl-feedback-block transl-feedback-partial"
        fb_icon = "≈"
    else:
        fb_class = "transl-feedback-block transl-feedback-wrong"
        fb_icon = "✗"

    answered_block = f"""\
<div class="{fb_class}">
  <div class="transl-answered-en">"{english}"</div>
  <div class="transl-answered-es">{user_translation}</div>
  <div class="transl-fb-row">
    <span class="transl-fb-icon">{fb_icon}</span>
    <span class="transl-fb-text">{feedback}</span>
  </div>
  {chips_html}
</div>"""

    if next_index >= total:
        # ── Completion card ───────────────────────────────────────────────────
        avg_score = sum(new_scores) / len(new_scores) if new_scores else 0.0
        score_pct = int(avg_score * 100)
        praise = (
            "¡Excelente!"
            if score_pct >= 80
            else "¡Buen intento!"
            if score_pct >= 60
            else "Keep practising!"
        )
        errors_json_str = json.dumps(_build_error_list(sentences, new_corrections))

        html = f"""\
<div class="tutor-activity-card" id="activity-translation">
  <div class="activity-header">
    <span class="transl-badge">📝 Translation complete</span>
    <span class="drill-progress">{new_correct} / {total}</span>
  </div>
  <div class="transl-complete">
    {answered_block}
    <p class="transl-score">{score_pct}%</p>
    <p class="transl-score-label">{praise}</p>
  </div>
  <form hx-post="/tutor/translation/complete"
        hx-target="#tutor-chat"
        hx-swap="beforeend"
        hx-on::after-request="scrollChat()"
        class="drill-done-form">
    <input type="hidden" name="session_id" value="{session_id}">
    <input type="hidden" name="score" value="{avg_score:.3f}">
    <input type="hidden" name="errors_json" value="{_escape_attr(errors_json_str)}">
    <input type="hidden" name="total" value="{total}">
    <button type="submit" class="drill-continue-btn">Continue →</button>
  </form>
</div>"""
        return html, True

    # ── Mid-challenge card — next sentence ────────────────────────────────────
    pct = next_index / total * 100
    next_sentence = sentences[next_index]

    hints_html = ""
    if hints:
        hint_items = "".join(f"<li>{h}</li>" for h in hints)
        hints_html = f"""\
<details class="transl-hints">
  <summary class="transl-hints-toggle">💡 Show hints</summary>
  <ul class="transl-hints-list">{hint_items}</ul>
</details>"""

    html = f"""\
<div class="tutor-activity-card" id="activity-translation">
  <div class="drill-progress-bar"><div class="drill-progress-bar-fill" style="width:{pct:.1f}%"></div></div>
  <div class="activity-header">
    <span class="transl-badge">📝 Translation</span>
    <span class="drill-progress">{next_index + 1} / {total}</span>
  </div>
  <div class="transl-item">
    {answered_block}
    <p class="transl-prompt">{next_sentence}</p>
    {hints_html}
  </div>
  <form hx-post="/tutor/translation/answer"
        hx-target="#activity-translation"
        hx-swap="outerHTML"
        hx-disabled-elt="find button"
        class="transl-input-form"
        id="transl-form">
    <input type="hidden" name="session_id"        value="{session_id}">
    <input type="hidden" name="sentences_json"    value="{_escape_attr(json.dumps(sentences))}">
    <input type="hidden" name="current_index"     value="{next_index}">
    <input type="hidden" name="correct_count"     value="{new_correct}">
    <input type="hidden" name="scores_json"       value="{_escape_attr(json.dumps(new_scores))}">
    <input type="hidden" name="corrections_json"  value="{_escape_attr(json.dumps(new_corrections))}">
    <input type="hidden" name="target_grammar"    value="{_escape_attr(target_grammar)}">
    <input type="hidden" name="difficulty"        value="{difficulty}">
    <input type="hidden" name="hints_json"        value="{_escape_attr(json.dumps(hints))}">
    <input type="hidden" name="worker_briefing"   value="{_escape_attr(worker_briefing)}">
    <textarea name="user_translation"
              placeholder="Type your Spanish translation..."
              class="transl-input"
              autocomplete="off"
              autocorrect="off"
              autocapitalize="off"
              spellcheck="false"
              rows="2"
              autofocus></textarea>
    <button type="submit" class="drill-submit-btn">Check →</button>
  </form>
</div>"""
    return html, False


def tool_show_translation_challenge(
    params: dict[str, Any], session: TutorSession
) -> ToolResult:
    """Render a translation challenge — shows English sentences one at a time."""
    tutor_message = params.get("tutor_message", "Translate each sentence into Spanish.")
    sentences: list[str] = params.get("sentences", [])
    target_grammar = params.get("target_grammar", "")
    difficulty = int(params.get("difficulty", 2))
    hints: list[str] = params.get("hints", [])
    worker_briefing = params.get("worker_briefing", "")

    if not sentences:
        return ToolResult(
            html=_render(
                "partials/tutor_message.html",
                message="(Translation challenge unavailable — no sentences provided.)",
                is_feedback=False,
                show_stats=False,
                stats={},
                show_input=False,
                plan_preview="",
                session_id=session.session_id,
            ),
            result_summary="Translation challenge unavailable: no sentences.",
        )

    first = sentences[0]
    html = _render(
        "partials/tutor_activity_translation.html",
        session_id=session.session_id,
        tutor_message=tutor_message,
        sentence=first,
        sentences_json=json.dumps(sentences),
        current_index=0,
        total=len(sentences),
        hints=hints,
        hints_json=json.dumps(hints),
        target_grammar=target_grammar,
        difficulty=difficulty,
        worker_briefing=worker_briefing,
        correct_count=0,
        scores_json="[]",
        corrections_json="[]",
    )

    return ToolResult(
        html=html,
        result_summary=(
            f"Translation challenge started: {len(sentences)} sentences "
            f"targeting {target_grammar}."
        ),
        activity_data={
            "sentences": sentences,
            "target_grammar": target_grammar,
            "difficulty": difficulty,
        },
    )


# ── Tool: show_circumlocution_challenge ───────────────────────────────────────


def _evaluate_circumlocution(
    prompt_en: str,
    learner_response: str,
    target_grammar: str,
    vocabulary_level: str,
    worker_briefing: str,
) -> dict[str, Any]:
    """
    Call gpt-4o-mini to evaluate a circumlocution attempt on three dimensions:
    communication_score, grammar_score, resourcefulness_score.
    Falls back gracefully if AI is unavailable.
    """
    if not ai_available():
        return _circumlocution_fallback()

    client = _get_client()
    if client is None:
        return _circumlocution_fallback()

    system = f"""\
You are an expert Spanish language evaluator focused on practical oral/written production.

THE TASK: The learner was given a complex English idea and asked to express it in Spanish
using whatever vocabulary they have. This is a CIRCUMLOCUTION exercise — the goal is
communication strategy, not word-for-word accuracy.

VOCABULARY LEVEL: {vocabulary_level} — the learner does NOT have advanced vocabulary.
They will use simple words and structures. That is expected. That is the point.

EVALUATION DIMENSIONS — score each 0.0 to 1.0:

1. COMMUNICATION SUCCESS (most important)
   Did the listener understand the core idea? Partial credit for partial ideas.
   - 0.9-1.0: Core idea fully conveyed, listener would understand
   - 0.7-0.9: Main idea conveyed, minor gaps or ambiguity
   - 0.5-0.7: Partial idea conveyed, listener might be confused
   - <0.5: Core idea lost or incomprehensible

2. GRAMMAR ACCURACY
   How correct was the Spanish? Focus on the TARGET GRAMMAR: {target_grammar}
   - Do NOT penalise for missing advanced vocabulary
   - DO flag persistent patterns (wrong tense choice, agreement errors)
   - 0.9-1.0: Target grammar correct, minor slips elsewhere
   - 0.7-0.9: Target grammar mostly correct, some errors
   - 0.5-0.7: Multiple grammar errors, target grammar often wrong
   - <0.5: Grammar makes response hard to parse

3. RESOURCEFULNESS (celebrate this!)
   Did the learner use creative workarounds to compensate for vocabulary gaps?
   Award HIGH scores for ANY of these strategies:
   - Negation: "no fue bueno" for "was bad/demanding"
   - Circumlocution: "la persona de mi trabajo" for "colleague"
   - Simplification: "quise más dinero" for "I wanted higher pay"
   - Explanation: "el lugar donde trabajo" for "workplace"
   - Cognates: using Spanish cognates or near-cognates correctly
   - Workarounds that convey the idea even if imprecise
   Score 0.8+ if ANY workaround appears. Score 0.9+ for multiple creative ones.

WORKAROUNDS TO EXPLICITLY CELEBRATE in this task:
{worker_briefing or "Any creative simplification that gets the idea across."}

TARGET GRAMMAR: {target_grammar}

WORKER BRIEFING (from the session tutor):
{worker_briefing or "Evaluate at the vocabulary_level ceiling. Communication > grammar."}

Respond ONLY with valid JSON in this exact format:
{{
  "communication_score": 0.85,
  "grammar_score": 0.70,
  "resourcefulness_score": 0.90,
  "communicated_successfully": true,
  "feedback": "2-3 sentences of specific, encouraging feedback. Quote their words. Celebrate workarounds explicitly.",
  "workarounds": [
    "Used 'mi jefe no fue bueno' for 'demanding boss' — exactly right!",
    "Used 'quise más dinero' for 'wanted more money' — natural and correct"
  ],
  "corrections": [
    {{"original": "phrase they wrote", "corrected": "better form", "explanation": "brief reason"}}
  ]
}}

Rules:
- feedback: start with what worked. Only mention corrections after praise. Max 3 sentences.
- workarounds: list EVERY creative simplification you spotted. Empty list if none found.
- corrections: max 3. Only flag genuine grammar errors, not vocabulary choices.
- If the learner tried hard but failed to communicate: give a resourcefulness score for effort."""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": (
                        f"English prompt: {prompt_en}\n\n"
                        f"Learner's Spanish response: {learner_response}"
                    ),
                },
            ],
            temperature=0.2,
            max_tokens=600,
        )
        raw = (response.choices[0].message.content or "").strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        result: dict[str, Any] = json.loads(raw)
        for key in ("communication_score", "grammar_score", "resourcefulness_score"):
            result[key] = max(0.0, min(1.0, float(result.get(key, 0.7))))
        result.setdefault(
            "communicated_successfully", result["communication_score"] >= 0.5
        )
        result.setdefault("feedback", "")
        result.setdefault("workarounds", [])
        result.setdefault("corrections", [])
        return result
    except Exception:
        return _circumlocution_fallback()


def _circumlocution_fallback() -> dict[str, Any]:
    return {
        "communication_score": 0.7,
        "grammar_score": 0.7,
        "resourcefulness_score": 0.7,
        "communicated_successfully": True,
        "feedback": "Nice attempt! (AI evaluation unavailable — keep practising.)",
        "workarounds": [],
        "corrections": [],
    }


def _circ_score_bar(label: str, score: float, colour_class: str) -> str:
    """Render a labelled score bar for the circumlocution results card."""
    pct = int(score * 100)
    return f"""\
<div class="circ-score-row">
  <span class="circ-score-label">{label}</span>
  <div class="circ-score-bar-bg">
    <div class="circ-score-bar-fill {colour_class}" style="width:{pct}%"></div>
  </div>
  <span class="circ-score-pct">{pct}%</span>
</div>"""


def render_circumlocution_result(
    prompt_en: str,
    learner_response: str,
    session_id: str,
    target_grammar: str,
    vocabulary_level: str,
    hints: list[str],
    worker_briefing: str,
) -> tuple[str, float]:
    """
    Evaluate a circumlocution response and render the results card.
    Returns (html, weighted_score).
    """
    eval_result = _evaluate_circumlocution(
        prompt_en=prompt_en,
        learner_response=learner_response,
        target_grammar=target_grammar,
        vocabulary_level=vocabulary_level,
        worker_briefing=worker_briefing,
    )

    comm = eval_result["communication_score"]
    gram = eval_result["grammar_score"]
    res = eval_result["resourcefulness_score"]
    # Weighted score: communication is primary, grammar and resourcefulness secondary
    weighted = comm * 0.5 + gram * 0.25 + res * 0.25

    feedback = eval_result.get("feedback", "")
    workarounds: list[str] = eval_result.get("workarounds", [])
    corrections: list[dict[str, Any]] = eval_result.get("corrections", [])

    # Score bars
    bars_html = (
        _circ_score_bar("Communication", comm, "circ-bar-comm")
        + _circ_score_bar("Grammar", gram, "circ-bar-gram")
        + _circ_score_bar("Resourcefulness", res, "circ-bar-res")
    )

    # Workaround highlights
    workarounds_html = ""
    if workarounds:
        items = "".join(
            f'<li class="circ-workaround-item">✦ {w}</li>' for w in workarounds
        )
        workarounds_html = (
            '<div class="circ-workarounds">'
            '<p class="circ-section-label">Creative workarounds</p>'
            f'<ul class="circ-workaround-list">{items}</ul>'
            "</div>"
        )

    # Correction chips
    chips_html = ""
    if corrections:
        chips = "".join(
            f'<span class="corr-chip" title="{_escape_attr(c.get("explanation", ""))}">'
            f"<del>{c.get('original', '')}</del> → {c.get('corrected', '')}</span>"
            for c in corrections
        )
        chips_html = (
            '<div class="circ-corrections">'
            '<p class="circ-section-label">Corrections</p>'
            f'<div class="correction-chips">{chips}</div>'
            "</div>"
        )

    errors_for_db = [
        f"{c.get('original')} → {c.get('corrected')}" for c in corrections[:8]
    ]

    praise = (
        "¡Excelente!"
        if weighted >= 0.8
        else "¡Buen trabajo!"
        if weighted >= 0.65
        else "Keep practising!"
    )

    html = f"""\
<div class="tutor-activity-card" id="activity-circumlocution">
  <div class="activity-header">
    <span class="circ-badge">🗣 Results</span>
  </div>
  <div class="circ-prompt-box circ-prompt-box-done">
    <p class="circ-prompt-text">{prompt_en}</p>
  </div>
  <div class="circ-response-box">
    <p class="circ-section-label">Your response</p>
    <p class="circ-response-text">{learner_response}</p>
  </div>
  <div class="circ-scores">
    {bars_html}
  </div>
  <div class="circ-feedback">
    <p class="circ-feedback-text">{feedback}</p>
  </div>
  {workarounds_html}
  {chips_html}
  <p class="transl-score-label" style="margin-top:0.5rem">{praise} · {int(weighted * 100)}% overall</p>
  <form hx-post="/tutor/circumlocution/complete"
        hx-target="#tutor-chat"
        hx-swap="beforeend"
        hx-on::after-request="scrollChat()"
        class="drill-done-form">
    <input type="hidden" name="session_id"    value="{session_id}">
    <input type="hidden" name="score"         value="{weighted:.3f}">
    <input type="hidden" name="comm_score"    value="{comm:.3f}">
    <input type="hidden" name="gram_score"    value="{gram:.3f}">
    <input type="hidden" name="res_score"     value="{res:.3f}">
    <input type="hidden" name="errors_json"   value="{_escape_attr(json.dumps(errors_for_db))}">
    <button type="submit" class="drill-continue-btn">Continue →</button>
  </form>
</div>"""

    return html, weighted


def tool_show_circumlocution_challenge(
    params: dict[str, Any], session: TutorSession
) -> ToolResult:
    """Render a circumlocution challenge card — one complex English prompt, free response."""
    tutor_message = params.get(
        "tutor_message", "Express this idea in Spanish using the words you know."
    )
    prompt_en = params.get("prompt_en", "")
    target_grammar = params.get("target_grammar", "")
    vocabulary_level = params.get("vocabulary_level", "intermediate")
    hints: list[str] = params.get("hints", [])
    worker_briefing = params.get("worker_briefing", "")

    if not prompt_en:
        return ToolResult(
            html=_render(
                "partials/tutor_message.html",
                message="(Circumlocution challenge unavailable — no prompt provided.)",
                is_feedback=False,
                show_stats=False,
                stats={},
                show_input=False,
                plan_preview="",
                session_id=session.session_id,
            ),
            result_summary="Circumlocution challenge unavailable: no prompt.",
        )

    html = _render(
        "partials/tutor_activity_circumlocution.html",
        session_id=session.session_id,
        tutor_message=tutor_message,
        prompt_en=prompt_en,
        target_grammar=target_grammar,
        vocabulary_level=vocabulary_level,
        hints=hints,
        hints_json=json.dumps(hints),
        worker_briefing=worker_briefing,
    )

    return ToolResult(
        html=html,
        result_summary=(
            f"Circumlocution challenge started: '{prompt_en[:60]}...' "
            f"targeting {target_grammar}."
        ),
        activity_data={
            "prompt_en": prompt_en,
            "target_grammar": target_grammar,
            "vocabulary_level": vocabulary_level,
        },
    )


# ── Dispatcher ────────────────────────────────────────────────────────────────

_TOOL_MAP = {
    "propose_session_plan": tool_propose_session_plan,
    "start_conversation": tool_start_conversation,
    "show_conjugation_drill": tool_show_conjugation_drill,
    "show_translation_challenge": tool_show_translation_challenge,
    "show_circumlocution_challenge": tool_show_circumlocution_challenge,
    "give_feedback": tool_give_feedback,
    "end_session": tool_end_session,
    "update_session_journal": tool_update_session_journal,
    "update_grammar_notes": tool_update_grammar_notes,
}


def execute_tool(
    tool_name: str, params: dict[str, Any], session: TutorSession
) -> ToolResult:
    """Dispatch a planner tool call to its implementation."""
    fn = _TOOL_MAP.get(tool_name)
    if fn is None:
        return ToolResult(
            html=f'<div class="tutor-message"><div class="tutor-bubble"><p class="tutor-text">Unknown tool: {tool_name}</p></div></div>',
            result_summary=f"Unknown tool: {tool_name}",
        )
    return fn(params, session)


# ── Conversation turn renderer (used by routes) ───────────────────────────────


def render_conversation_turn(
    user_message: str,
    ai_reply: str,
    corrections: list[Any],
    persona_name: str,
    turns_done: int,
    max_turns: int,
    session_id: str,
    conv_state_json: str,
) -> str:
    """Render one conversation exchange (user bubble + AI reply bubble)."""
    safe_user = html.escape(user_message)
    safe_persona = html.escape(persona_name)
    ai_reply_html = make_words_tappable(ai_reply)

    # Correction chips
    chips_html = ""
    if corrections:
        chips = "".join(
            f'<span class="corr-chip" title="{html.escape(c.explanation)}">'
            f"<del>{html.escape(c.original)}</del> → {html.escape(c.corrected)}</span>"
            for c in corrections
        )
        chips_html = f'<div class="correction-chips">{chips}</div>'

    user_turns_done = turns_done + 1
    at_limit = user_turns_done >= max_turns

    next_input_inner = ""
    if not at_limit:
        next_input_inner = f"""\
<form hx-post="/tutor/conversation/respond"
      hx-target="#conv-messages"
      hx-swap="beforeend"
      hx-sync="this:drop"
      hx-disabled-elt="find button"
      hx-on::after-request="this.reset(); scrollConv()"
      class="conv-input-form">
  <input type="hidden" name="session_id" value="{session_id}">
  <input type="hidden" name="conv_state" value="{_escape_attr(conv_state_json)}">
  <input type="hidden" name="turns_done" value="{user_turns_done}">
  <input type="hidden" name="max_turns" value="{max_turns}">
  <input type="text"
         name="user_message"
         placeholder="Reply in Spanish..."
         class="conv-input"
         autocomplete="off"
         autofocus>
  <button type="submit" class="conv-send-btn">→</button>
</form>"""
    else:
        # Conversation finished — submit to complete endpoint
        next_input_inner = f"""\
<form hx-post="/tutor/conversation/complete"
      hx-target="#tutor-chat"
      hx-swap="beforeend"
      hx-sync="this:drop"
      hx-disabled-elt="find button"
      hx-on::after-request="scrollChat()"
      class="conv-done-form"
      id="conv-done-form">
  <input type="hidden" name="session_id" value="{session_id}">
  <input type="hidden" name="conv_state" value="{_escape_attr(conv_state_json)}">
  <button type="submit" class="conv-done-btn">Finish conversation →</button>
</form>"""

    return f"""\
<div class="conv-message user-message">
  <span class="conv-speaker">You</span>
  <p class="conv-text">{safe_user}</p>
  {chips_html}
</div>
<div class="conv-message ai-message" data-chat-role="ai">
  <span class="conv-speaker">{safe_persona}</span>
  <p class="conv-text">{ai_reply_html}</p>
</div>
<span class="turn-counter" id="turn-counter" hx-swap-oob="outerHTML">{user_turns_done} / {max_turns}</span>
<div id="conv-input-slot" hx-swap-oob="innerHTML">{next_input_inner}</div>"""


# ── HTML escaping for attribute values ────────────────────────────────────────


def _escape_attr(s: str) -> str:
    """Escape a string for use in an HTML attribute value (double-quoted)."""
    return (
        s.replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


__all__ = [
    "ToolResult",
    "TutorActivityResult",
    "execute_tool",
    "render_conversation_turn",
    "render_drill_answer",
    "render_translation_answer",
    "render_circumlocution_result",
]
