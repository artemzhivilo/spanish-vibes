"""SQLite-backed learner data layer with spaced repetition tracking.

Provides persistent storage for learner profiles, grammar tracking,
word-level spaced repetition (SM-2), and session history. Uses Python's
built-in sqlite3 module -- no ORM for Phase 1.

The database lives at app/data/spanish_vibes.db.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

APP_DIR = Path(__file__).parent
DB_DIR = APP_DIR / "data"
DB_PATH = DB_DIR / "spanish_vibes.db"


def _connect() -> sqlite3.Connection:
    """Return a connection with row_factory set to sqlite3.Row."""
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS learner_profile (
    learner_id  TEXT PRIMARY KEY,
    display_name TEXT,
    cefr_level  TEXT DEFAULT 'A1',
    interests   TEXT,           -- JSON array of interest strings
    notes_md    TEXT,           -- Marta's freeform notes (existing markdown)
    created_at  TEXT DEFAULT (datetime('now')),
    updated_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS grammar_status (
    learner_id  TEXT,
    topic       TEXT,
    status      TEXT DEFAULT 'untested',   -- solid, shaky, gap, untested
    evidence    TEXT,                       -- JSON array of evidence entries
    last_tested TEXT,
    PRIMARY KEY (learner_id, topic),
    FOREIGN KEY (learner_id) REFERENCES learner_profile(learner_id)
);

CREATE TABLE IF NOT EXISTS word_tracking (
    learner_id     TEXT,
    word           TEXT,
    translation    TEXT,
    domain         TEXT,
    repetitions    INTEGER DEFAULT 0,
    ease_factor    REAL    DEFAULT 2.5,
    interval_days  REAL    DEFAULT 0,
    last_review    TEXT,
    next_review    TEXT,
    times_correct  INTEGER DEFAULT 0,
    times_wrong    INTEGER DEFAULT 0,
    PRIMARY KEY (learner_id, word),
    FOREIGN KEY (learner_id) REFERENCES learner_profile(learner_id)
);

CREATE TABLE IF NOT EXISTS session_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    learner_id  TEXT,
    session_date TEXT DEFAULT (date('now')),
    role        TEXT,       -- 'user' or 'assistant'
    content     TEXT,
    created_at  TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (learner_id) REFERENCES learner_profile(learner_id)
);
"""


def init_db() -> None:
    """Create all tables if they don't exist."""
    conn = _connect()
    try:
        conn.executescript(_SCHEMA)
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Learner profile helpers
# ---------------------------------------------------------------------------


def get_or_create_learner(learner_id: str) -> dict[str, Any]:
    """Return the learner profile as a dict, creating it if needed."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM learner_profile WHERE learner_id = ?",
            (learner_id,),
        ).fetchone()
        if row is not None:
            return dict(row)
        conn.execute(
            "INSERT INTO learner_profile (learner_id) VALUES (?)",
            (learner_id,),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM learner_profile WHERE learner_id = ?",
            (learner_id,),
        ).fetchone()
        return dict(row)
    finally:
        conn.close()


def update_learner_profile(learner_id: str, **kwargs: Any) -> None:
    """Update any profile fields. Only supplied kwargs are updated."""
    if not kwargs:
        return
    # Ensure learner exists
    get_or_create_learner(learner_id)
    allowed = {"display_name", "cefr_level", "interests", "notes_md"}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return
    fields["updated_at"] = datetime.now().isoformat()
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [learner_id]
    conn = _connect()
    try:
        conn.execute(
            f"UPDATE learner_profile SET {set_clause} WHERE learner_id = ?",
            values,
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Grammar status helpers
# ---------------------------------------------------------------------------


def get_grammar_status(learner_id: str) -> dict[str, dict[str, Any]]:
    """Return dict of topic -> {status, evidence, last_tested}."""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT topic, status, evidence, last_tested "
            "FROM grammar_status WHERE learner_id = ?",
            (learner_id,),
        ).fetchall()
        result: dict[str, dict[str, Any]] = {}
        for row in rows:
            evidence = json.loads(row["evidence"]) if row["evidence"] else []
            result[row["topic"]] = {
                "status": row["status"],
                "evidence": evidence,
                "last_tested": row["last_tested"],
            }
        return result
    finally:
        conn.close()


def update_grammar_status(
    learner_id: str,
    topic: str,
    status: str,
    evidence_entry: str | None = None,
) -> None:
    """Update grammar topic status, appending an evidence entry."""
    get_or_create_learner(learner_id)
    now = datetime.now().isoformat()
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT evidence FROM grammar_status WHERE learner_id = ? AND topic = ?",
            (learner_id, topic),
        ).fetchone()
        if row is not None:
            evidence = json.loads(row["evidence"]) if row["evidence"] else []
        else:
            evidence = []
        if evidence_entry:
            evidence.append({"entry": evidence_entry, "at": now})
            # Keep the last 20 evidence entries to avoid unbounded growth
            evidence = evidence[-20:]
        evidence_json = json.dumps(evidence)
        conn.execute(
            "INSERT INTO grammar_status (learner_id, topic, status, evidence, last_tested) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(learner_id, topic) DO UPDATE SET "
            "status = excluded.status, evidence = excluded.evidence, "
            "last_tested = excluded.last_tested",
            (learner_id, topic, status, evidence_json, now),
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Word tracking + SM-2 spaced repetition
# ---------------------------------------------------------------------------


def track_word(
    learner_id: str,
    word: str,
    translation: str,
    domain: str | None = None,
) -> None:
    """Add a word to tracking if it doesn't already exist."""
    get_or_create_learner(learner_id)
    now = datetime.now().isoformat()
    conn = _connect()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO word_tracking "
            "(learner_id, word, translation, domain, next_review) "
            "VALUES (?, ?, ?, ?, ?)",
            (learner_id, word.lower().strip(), translation, domain, now),
        )
        conn.commit()
    finally:
        conn.close()


def review_word(learner_id: str, word: str, quality: int) -> None:
    """SM-2 algorithm update for a word review.

    quality: 0-5
        5 = perfect response
        4 = correct after hesitation
        3 = correct with difficulty
        2 = incorrect, but close
        1 = incorrect
        0 = complete blank
    """
    quality = max(0, min(5, quality))
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT repetitions, ease_factor, interval_days, "
            "times_correct, times_wrong "
            "FROM word_tracking WHERE learner_id = ? AND word = ?",
            (learner_id, word.lower().strip()),
        ).fetchone()
        if row is None:
            return  # Word not tracked yet

        reps = row["repetitions"]
        ef = row["ease_factor"]
        interval = row["interval_days"]
        times_correct = row["times_correct"]
        times_wrong = row["times_wrong"]

        # SM-2 ease factor update
        ef = ef + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
        ef = max(1.3, ef)  # Clamp

        if quality < 3:
            # Failed: reset
            reps = 0
            interval = 1.0
            times_wrong += 1
        else:
            # Passed
            times_correct += 1
            if reps == 0:
                interval = 1.0
            elif reps == 1:
                interval = 6.0
            else:
                interval = interval * ef
            reps += 1

        now = datetime.now()
        last_review = now.isoformat()
        next_review = (now + timedelta(days=interval)).isoformat()

        conn.execute(
            "UPDATE word_tracking SET "
            "repetitions = ?, ease_factor = ?, interval_days = ?, "
            "last_review = ?, next_review = ?, "
            "times_correct = ?, times_wrong = ? "
            "WHERE learner_id = ? AND word = ?",
            (
                reps,
                ef,
                interval,
                last_review,
                next_review,
                times_correct,
                times_wrong,
                learner_id,
                word.lower().strip(),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_words_due(learner_id: str, limit: int = 20) -> list[dict[str, Any]]:
    """Return words where next_review <= now, oldest first."""
    now = datetime.now().isoformat()
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT word, translation, domain, repetitions, "
            "ease_factor, interval_days, last_review, next_review, "
            "times_correct, times_wrong "
            "FROM word_tracking "
            "WHERE learner_id = ? AND (next_review IS NULL OR next_review <= ?) "
            "ORDER BY next_review ASC "
            "LIMIT ?",
            (learner_id, now, limit),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_all_words(learner_id: str) -> list[dict[str, Any]]:
    """Return all tracked words for a learner."""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT word, translation, domain, repetitions, "
            "ease_factor, interval_days, last_review, next_review, "
            "times_correct, times_wrong "
            "FROM word_tracking WHERE learner_id = ? "
            "ORDER BY word ASC",
            (learner_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Session log helpers
# ---------------------------------------------------------------------------


def log_message(learner_id: str, role: str, content: str) -> None:
    """Log a message to the session log."""
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO session_log (learner_id, role, content) VALUES (?, ?, ?)",
            (learner_id, role, content),
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Learner summary (for system prompt injection)
# ---------------------------------------------------------------------------


def get_learner_summary(learner_id: str) -> str:
    """Return a formatted string summarizing the learner's data.

    This is injected into the system prompt so Marta has structured
    context about the learner alongside the freeform notes.
    """
    conn = _connect()
    try:
        profile = conn.execute(
            "SELECT * FROM learner_profile WHERE learner_id = ?",
            (learner_id,),
        ).fetchone()
        if profile is None:
            return ""

        parts: list[str] = []

        # -- Profile --
        parts.append("## Structured learner data")
        cefr = profile["cefr_level"] or "A1"
        parts.append(f"**CEFR level:** {cefr}")
        if profile["display_name"]:
            parts.append(f"**Name:** {profile['display_name']}")
        if profile["interests"]:
            try:
                interests = json.loads(profile["interests"])
                if interests:
                    parts.append(f"**Interests:** {', '.join(interests)}")
            except (json.JSONDecodeError, TypeError):
                pass

        # -- Grammar statuses --
        grammar_rows = conn.execute(
            "SELECT topic, status, last_tested "
            "FROM grammar_status WHERE learner_id = ? "
            "ORDER BY topic",
            (learner_id,),
        ).fetchall()
        if grammar_rows:
            status_map = {"solid": "+", "shaky": "~", "gap": "-", "untested": "?"}
            parts.append("\n**Grammar status:**")
            for row in grammar_rows:
                marker = status_map.get(row["status"], "?")
                parts.append(f"  [{marker}] {row['topic']} ({row['status']})")

        # -- Word stats --
        word_stats = conn.execute(
            "SELECT COUNT(*) as total, "
            "SUM(CASE WHEN next_review <= datetime('now') THEN 1 ELSE 0 END) as due, "
            "SUM(times_correct) as total_correct, "
            "SUM(times_wrong) as total_wrong "
            "FROM word_tracking WHERE learner_id = ?",
            (learner_id,),
        ).fetchone()
        if word_stats and word_stats["total"] > 0:
            parts.append(
                f"\n**Vocabulary:** {word_stats['total']} words tracked, "
                f"{word_stats['due'] or 0} due for review, "
                f"{word_stats['total_correct'] or 0} correct / "
                f"{word_stats['total_wrong'] or 0} wrong lifetime"
            )
            # Show domains if any
            domain_rows = conn.execute(
                "SELECT domain, COUNT(*) as cnt "
                "FROM word_tracking "
                "WHERE learner_id = ? AND domain IS NOT NULL "
                "GROUP BY domain ORDER BY cnt DESC LIMIT 5",
                (learner_id,),
            ).fetchall()
            if domain_rows:
                domains = [f"{r['domain']} ({r['cnt']})" for r in domain_rows]
                parts.append(f"**Vocab domains:** {', '.join(domains)}")

        # -- Words due (show top 10 for prompt) --
        due_words = conn.execute(
            "SELECT word, translation "
            "FROM word_tracking "
            "WHERE learner_id = ? AND (next_review IS NULL OR next_review <= datetime('now')) "
            "ORDER BY next_review ASC LIMIT 10",
            (learner_id,),
        ).fetchall()
        if due_words:
            word_list = [f"{r['word']} ({r['translation']})" for r in due_words]
            parts.append(
                f"\n**Words due for review (weave into conversation):** "
                f"{', '.join(word_list)}"
            )

        return "\n".join(parts)
    finally:
        conn.close()
