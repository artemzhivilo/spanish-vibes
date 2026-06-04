"""Narrative memory system for the agent-based tutor.

Each learner has three markdown files under data/learners/{user_id}/:
  learner_profile.md  — who they are, style, interests, level
  session_journal.md  — append-only log of what happened each session
  grammar_notes.md    — per-concept mastery tracking with evidence

The planner reads all memory sources at session start (~2-3K tokens total) via
build_planner_context(), and updates them at session end through the
update_session_journal / update_grammar_notes / rewrite_learner_profile
tool calls.

New learners get default content copied from data/templates/ so the
planner always has a well-structured starting point.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .bkt import MASTERY_THRESHOLD, MIN_ATTEMPTS_FOR_MASTERY
from .concepts import load_concepts
from .flow_db import get_all_concept_knowledge


# ── Paths ──────────────────────────────────────────────────────────────────────

_PACKAGE_ROOT = Path(__file__).resolve().parent
_PROJECT_ROOT = _PACKAGE_ROOT.parent.parent
DATA_DIR = _PROJECT_ROOT / "data"
LEARNERS_DIR = DATA_DIR / "learners"
_TEMPLATES_DIR = DATA_DIR / "templates"


# ── Default content (fallback if template files are missing) ───────────────────

_DEFAULT_LEARNER_PROFILE = """\
# Learner Profile: New Learner
Updated: (first session — profile will be written after initial assessment)

## Level & Stage
New learner — not yet assessed. Start easy, observe performance, and
calibrate after a guided first activity.

## Current Focus
Not yet established. First session goal: assess level and identify the
biggest gap to work on.

## Learning Style
Unknown — observe during this session.

## Interests & Life Context
Not yet captured. Discover naturally during early activities.

## Goals
Not yet discussed. Discover the learner's goals through conversation.
Exam Prep (optional): not yet discussed. If they want exam alignment,
capture which exam and timeline here.
"""

_DEFAULT_GRAMMAR_NOTES = """\
# Grammar Tracking

No data yet. First session will establish baseline.

After the first session, add sections for each concept practised:

## [Concept Name]
Status: WEAK / IN_PROGRESS / SOLID / AVOIDANCE / NOT_YET_INTRODUCED
Evidence: [specific examples with dates and context]
"""

_DEFAULT_SESSION_JOURNAL = """\
# Session Journal

No sessions recorded yet. This is the first session.
"""


# ── Low-level file helpers ─────────────────────────────────────────────────────


def _read_file(path: Path, default: str = "") -> str:
    """Read a file, returning `default` if it doesn't exist."""
    try:
        return path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return default


def _write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.strip() + "\n", encoding="utf-8")


def _load_template(name: str, fallback: str) -> str:
    """Load a template from data/templates/, falling back to embedded default."""
    return _read_file(_TEMPLATES_DIR / name, fallback)


# ── Directory helpers ──────────────────────────────────────────────────────────


def get_learner_dir(user_id: str) -> Path:
    """Return the learner directory path (does NOT create it)."""
    return LEARNERS_DIR / user_id


def ensure_learner_dir(user_id: str) -> Path:
    """Return the learner directory, creating it if it doesn't exist."""
    d = get_learner_dir(user_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


# ── Read API ───────────────────────────────────────────────────────────────────


def read_learner_profile(user_id: str) -> str:
    """Return learner_profile.md, defaulting to new-learner template."""
    default = _load_template("new_learner_profile.md", _DEFAULT_LEARNER_PROFILE)
    return _read_file(ensure_learner_dir(user_id) / "learner_profile.md", default)


def read_session_journal(user_id: str, last_n: int = 5) -> str:
    """Return the last `last_n` session journal entries.

    Entries are delimited by '## 20…' headings.  Older entries are
    silently dropped so the planner context stays compact.
    """
    full = _read_file(
        ensure_learner_dir(user_id) / "session_journal.md",
        _DEFAULT_SESSION_JOURNAL,
    )
    lines = full.splitlines()
    entry_starts = [i for i, ln in enumerate(lines) if ln.startswith("## 20")]
    if len(entry_starts) <= last_n:
        return full
    cutoff = entry_starts[-last_n]
    # Keep the file-level heading (# …) and all entries from cutoff onwards
    header_lines = [ln for ln in lines[:cutoff] if ln.startswith("# ")]
    return "\n".join(header_lines + lines[cutoff:])


def read_grammar_notes(user_id: str) -> str:
    """Return grammar_notes.md, defaulting to the starter template."""
    default = _load_template("new_grammar_notes.md", _DEFAULT_GRAMMAR_NOTES)
    return _read_file(ensure_learner_dir(user_id) / "grammar_notes.md", default)


def _is_concept_mastered(p_mastery: float, n_attempts: int) -> bool:
    return p_mastery >= MASTERY_THRESHOLD and n_attempts >= MIN_ATTEMPTS_FOR_MASTERY


def _tier_name(tier: int) -> str:
    names = {
        1: "Foundations",
        2: "Basic Grammar",
        3: "Applied Communication",
        4: "Core Verbs & Adjectives",
        5: "Present Tense",
        6: "Daily Life",
        7: "Past Tense",
        8: "Advanced Grammar",
    }
    return names.get(tier, f"Level {tier}")


def build_curriculum_context(user_id: str) -> str:
    """Build a compact curriculum summary from concepts + BKT state.

    Always shows the concept tier layout from the YAML graph.
    BKT mastery detail is shown when available (after Flow Mode practice).
    """
    _ = user_id  # reserved for future per-user curriculum customizations

    try:
        concepts = load_concepts()
    except Exception:
        return "Curriculum data unavailable."

    if not concepts:
        return "No concepts defined in curriculum."

    # Build tier map from concept graph (always available)
    tiers: dict[int, list[str]] = {}
    for concept_id, concept in concepts.items():
        tier = int(getattr(concept, "difficulty_level", 1))
        tiers.setdefault(tier, []).append(concept_id)

    # Load BKT knowledge (only present after Flow Mode practice)
    try:
        knowledge = get_all_concept_knowledge()
    except Exception:
        knowledge = {}

    has_bkt_data = bool(knowledge) and any(
        ck.n_attempts > 0 for ck in knowledge.values()
    )

    # ── Tier summary lines ─────────────────────────────────────────────────────
    tier_stats: dict[
        int, tuple[int, int, int]
    ] = {}  # tier → (mastered, in_progress, total)
    for tier in sorted(tiers):
        concept_ids = tiers[tier]
        total = len(concept_ids)
        mastered = in_progress = 0
        for concept_id in concept_ids:
            ck = knowledge.get(concept_id)
            if ck and _is_concept_mastered(ck.p_mastery, ck.n_attempts):
                mastered += 1
            elif ck and ck.n_attempts > 0:
                in_progress += 1
        tier_stats[tier] = (mastered, in_progress, total)

    # Determine current tier (first tier not fully mastered)
    current_tier = sorted(tiers)[0] if tiers else 1
    for tier in sorted(tiers):
        mastered, _, total = tier_stats[tier]
        if mastered < total:
            current_tier = tier
            break

    current_mastered, _, current_total = tier_stats.get(current_tier, (0, 0, 0))
    current_pct = (
        round((current_mastered / current_total) * 100) if current_total else 0
    )

    tier_lines: list[str] = []
    for tier in sorted(tiers):
        mastered, in_prog, total = tier_stats[tier]
        concept_ids = sorted(tiers[tier])
        if has_bkt_data:
            suffix = f", {in_prog} in progress" if in_prog else ""
            tier_lines.append(
                f"Tier {tier} ({_tier_name(tier)}): {mastered}/{total} mastered{suffix}"
            )
        else:
            # No BKT data: list concept IDs so planner knows what exists
            concept_list = ", ".join(concept_ids[:8])
            ellipsis = (
                f" (+{len(concept_ids) - 8} more)" if len(concept_ids) > 8 else ""
            )
            tier_lines.append(
                f"Tier {tier} ({_tier_name(tier)}): {total} concepts — {concept_list}{ellipsis}"
            )

    lines: list[str] = [
        f"Current tier: {current_tier} ({_tier_name(current_tier)})"
        + (f" — {current_pct}% mastered" if has_bkt_data else " — not yet assessed"),
        *tier_lines,
    ]

    if not has_bkt_data:
        lines.append("")
        lines.append(
            "BKT mastery: no data yet (unlocked after Flow Mode practice). "
            "Start with Tier 1 concepts above."
        )
        # Still list Tier 1 entry points so planner can target them
        tier1_concepts = sorted(tiers.get(1, []))
        if tier1_concepts:
            lines.append(
                "Recommended starting concepts: " + ", ".join(tier1_concepts[:6])
            )
        return "\n".join(lines)

    # ── BKT detail (only when data exists) ────────────────────────────────────
    in_progress_rows: list[tuple[str, float, int]] = []
    stuck_rows: list[tuple[str, float, int]] = []
    for concept_id, ck in knowledge.items():
        if concept_id not in concepts:
            continue
        if 0.3 < ck.p_mastery < 0.9 and ck.n_attempts > 0:
            in_progress_rows.append((concept_id, ck.p_mastery, ck.n_attempts))
        if ck.n_attempts >= 6 and ck.p_mastery < 0.7:
            stuck_rows.append((concept_id, ck.p_mastery, ck.n_attempts))

    in_progress_rows.sort(key=lambda item: (item[1], -item[2]))
    stuck_rows.sort(key=lambda item: (-item[2], item[1]))

    # Next available: no attempts yet, prerequisites met
    next_available: list[str] = []
    for concept_id, concept in sorted(
        concepts.items(),
        key=lambda item: (int(getattr(item[1], "difficulty_level", 1)), item[0]),
    ):
        ck = knowledge.get(concept_id)
        if ck and ck.n_attempts > 0:
            continue
        prereqs_met = all(
            (
                knowledge.get(p) is not None
                and _is_concept_mastered(
                    knowledge[p].p_mastery, knowledge[p].n_attempts
                )
            )
            for p in concept.prerequisites
        )
        if prereqs_met:
            next_available.append(concept_id)
        if len(next_available) >= 5:
            break

    if in_progress_rows:
        lines.append("")
        lines.append("In progress:")
        for concept_id, mastery, attempts in in_progress_rows[:5]:
            lines.append(
                f"  {concept_id} — {mastery:.2f} mastery ({attempts} attempts)"
            )

    if next_available:
        lines.append("")
        lines.append("Next available: " + ", ".join(next_available))

    if stuck_rows:
        lines.append("")
        for concept_id, mastery, attempts in stuck_rows[:3]:
            lines.append(
                f"Avoidance alert: {concept_id} — {attempts} attempts, "
                f"only {mastery:.2f} mastery. Needs focused drill."
            )

    return "\n".join(lines)


# ── Write API ──────────────────────────────────────────────────────────────────


def write_learner_profile(user_id: str, content: str) -> None:
    """Replace learner_profile.md with a freshly written version."""
    _write_file(ensure_learner_dir(user_id) / "learner_profile.md", content)


def append_session_journal(user_id: str, entry: str) -> None:
    """Append a new dated entry to session_journal.md."""
    path = ensure_learner_dir(user_id) / "session_journal.md"
    existing = _read_file(path, _DEFAULT_SESSION_JOURNAL)
    # Strip one-time default boilerplate so it never confuses new-learner detection
    if "No sessions recorded yet" in existing:
        existing = "# Session Journal"
    _write_file(path, f"{existing}\n\n{entry.strip()}")


def write_grammar_notes(user_id: str, content: str) -> None:
    """Replace grammar_notes.md with new content (full overwrite)."""
    _write_file(ensure_learner_dir(user_id) / "grammar_notes.md", content)


def update_grammar_concept(
    user_id: str,
    concept: str,
    status: str | None,
    update_text: str,
) -> None:
    """Append a dated update block for one concept inside grammar_notes.md.

    If a '## {concept}' section already exists the block is inserted at
    the end of that section (before the next '## ').  Otherwise it's
    appended at the end of the file.
    """
    path = ensure_learner_dir(user_id) / "grammar_notes.md"
    existing = _read_file(path, _DEFAULT_GRAMMAR_NOTES)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    block = f"\n\n### Update {date_str} — {concept}\n"
    if status:
        block += f"Status: {status}\n"
    block += update_text.strip()

    header = f"## {concept}"
    if header in existing:
        next_h2 = existing.find("\n## ", existing.rfind(header) + 1)
        existing = (
            existing + block
            if next_h2 == -1
            else existing[:next_h2] + block + existing[next_h2:]
        )
    else:
        existing += block

    _write_file(path, existing)


# ── Planner context builder ────────────────────────────────────────────────────


def build_planner_context(user_id: str) -> str:
    """Assemble memory files + curriculum summary into planner context.

    Format matches the architecture doc:
      ## LEARNER PROFILE
      ## RECENT SESSIONS (last 5)
      ## GRAMMAR STATUS
      ## CURRICULUM STATUS
    """
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


# ── Backward-compat aliases (used by tutor_agent.py) ──────────────────────────

learner_dir = ensure_learner_dir
get_learner_profile = read_learner_profile
get_session_journal = read_session_journal  # param renamed: max_entries → last_n
get_grammar_notes = read_grammar_notes
append_journal_entry = append_session_journal
rewrite_learner_profile = write_learner_profile


# ── Public API ─────────────────────────────────────────────────────────────────

__all__ = [
    # Paths
    "DATA_DIR",
    "LEARNERS_DIR",
    "get_learner_dir",
    "ensure_learner_dir",
    # Read
    "read_learner_profile",
    "read_session_journal",
    "read_grammar_notes",
    "build_curriculum_context",
    "build_planner_context",
    # Write
    "write_learner_profile",
    "append_session_journal",
    "write_grammar_notes",
    "update_grammar_concept",
    # Backward-compat
    "learner_dir",
    "get_learner_profile",
    "get_session_journal",
    "get_grammar_notes",
    "append_journal_entry",
    "rewrite_learner_profile",
]
