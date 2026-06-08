"""Learner data layer with spaced repetition tracking.

Supports both SQLite (local dev) and PostgreSQL (production).
Detects which to use from the DATABASE_URL environment variable:
  - If DATABASE_URL is set and starts with "postgres", use PostgreSQL.
  - Otherwise, use SQLite at app/data/spanish_vibes.db.
"""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Generator

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

APP_DIR = Path(__file__).parent
DB_DIR = APP_DIR / "data"
DB_PATH = DB_DIR / "spanish_vibes.db"

DATABASE_URL = os.environ.get("DATABASE_URL", "")
USE_POSTGRES = DATABASE_URL.startswith("postgres")

if USE_POSTGRES:
    import psycopg2
    import psycopg2.extras


# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------


class _RowDict(dict):
    """Dict subclass that allows attribute access for column names."""

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name) from None


def _fix_pg_url(url: str) -> str:
    """Railway gives postgres:// but psycopg2 wants postgresql://."""
    if url.startswith("postgres://"):
        return "postgresql://" + url[len("postgres://") :]
    return url


@contextmanager
def _connect() -> Generator[Any, None, None]:
    """Yield a (conn, cursor_factory) pair. Handles commit/close."""
    if USE_POSTGRES:
        conn = psycopg2.connect(_fix_pg_url(DATABASE_URL))
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    else:
        DB_DIR.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def _execute(conn: Any, sql: str, params: tuple = ()) -> Any:
    """Execute SQL, adapting placeholder style for Postgres."""
    if USE_POSTGRES:
        # Convert ? placeholders to %s for psycopg2
        sql = sql.replace("?", "%s")
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    else:
        cur = conn.cursor()
    cur.execute(sql, params)
    return cur


def _fetchone(conn: Any, sql: str, params: tuple = ()) -> dict[str, Any] | None:
    """Execute and fetch one row as a dict."""
    cur = _execute(conn, sql, params)
    row = cur.fetchone()
    if row is None:
        return None
    if USE_POSTGRES:
        return dict(row)
    else:
        return dict(row)


def _fetchall(conn: Any, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    """Execute and fetch all rows as dicts."""
    cur = _execute(conn, sql, params)
    rows = cur.fetchall()
    if USE_POSTGRES:
        return [dict(r) for r in rows]
    else:
        return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA_SQLITE = """
CREATE TABLE IF NOT EXISTS learner_profile (
    learner_id  TEXT PRIMARY KEY,
    display_name TEXT,
    cefr_level  TEXT DEFAULT 'A1',
    interests   TEXT,
    notes_md    TEXT,
    created_at  TEXT DEFAULT (datetime('now')),
    updated_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS grammar_status (
    learner_id  TEXT,
    topic       TEXT,
    status      TEXT DEFAULT 'untested',
    evidence    TEXT,
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

CREATE TABLE IF NOT EXISTS chat_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    learner_id  TEXT NOT NULL,
    persona_id  TEXT NOT NULL,
    role        TEXT NOT NULL,
    content     TEXT NOT NULL,
    created_at  TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (learner_id) REFERENCES learner_profile(learner_id)
);

CREATE TABLE IF NOT EXISTS session_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    learner_id  TEXT,
    session_date TEXT DEFAULT (date('now')),
    role        TEXT,
    content     TEXT,
    created_at  TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (learner_id) REFERENCES learner_profile(learner_id)
);
"""

_SCHEMA_POSTGRES = """
CREATE TABLE IF NOT EXISTS learner_profile (
    learner_id  TEXT PRIMARY KEY,
    display_name TEXT,
    cefr_level  TEXT DEFAULT 'A1',
    interests   TEXT,
    notes_md    TEXT,
    created_at  TIMESTAMP DEFAULT NOW(),
    updated_at  TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS grammar_status (
    learner_id  TEXT,
    topic       TEXT,
    status      TEXT DEFAULT 'untested',
    evidence    TEXT,
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
    ease_factor    DOUBLE PRECISION DEFAULT 2.5,
    interval_days  DOUBLE PRECISION DEFAULT 0,
    last_review    TEXT,
    next_review    TEXT,
    times_correct  INTEGER DEFAULT 0,
    times_wrong    INTEGER DEFAULT 0,
    PRIMARY KEY (learner_id, word),
    FOREIGN KEY (learner_id) REFERENCES learner_profile(learner_id)
);

CREATE TABLE IF NOT EXISTS chat_log (
    id          SERIAL PRIMARY KEY,
    learner_id  TEXT NOT NULL,
    persona_id  TEXT NOT NULL,
    role        TEXT NOT NULL,
    content     TEXT NOT NULL,
    created_at  TIMESTAMP DEFAULT NOW(),
    FOREIGN KEY (learner_id) REFERENCES learner_profile(learner_id)
);

CREATE TABLE IF NOT EXISTS session_log (
    id          SERIAL PRIMARY KEY,
    learner_id  TEXT,
    session_date DATE DEFAULT CURRENT_DATE,
    role        TEXT,
    content     TEXT,
    created_at  TIMESTAMP DEFAULT NOW(),
    FOREIGN KEY (learner_id) REFERENCES learner_profile(learner_id)
);
"""


def init_db() -> None:
    """Create all tables if they don't exist."""
    with _connect() as conn:
        schema = _SCHEMA_POSTGRES if USE_POSTGRES else _SCHEMA_SQLITE
        if USE_POSTGRES:
            cur = conn.cursor()
            cur.execute(schema)
        else:
            conn.executescript(schema)


# ---------------------------------------------------------------------------
# Learner profile helpers
# ---------------------------------------------------------------------------


def get_or_create_learner(learner_id: str) -> dict[str, Any]:
    """Return the learner profile as a dict, creating it if needed."""
    with _connect() as conn:
        row = _fetchone(
            conn,
            "SELECT * FROM learner_profile WHERE learner_id = ?",
            (learner_id,),
        )
        if row is not None:
            return row
        _execute(
            conn,
            "INSERT INTO learner_profile (learner_id) VALUES (?)",
            (learner_id,),
        )
        row = _fetchone(
            conn,
            "SELECT * FROM learner_profile WHERE learner_id = ?",
            (learner_id,),
        )
        return row  # type: ignore[return-value]


def update_learner_profile(learner_id: str, **kwargs: Any) -> None:
    """Update any profile fields. Only supplied kwargs are updated."""
    if not kwargs:
        return
    get_or_create_learner(learner_id)
    allowed = {"display_name", "cefr_level", "interests", "notes_md"}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return
    fields["updated_at"] = datetime.now().isoformat()
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [learner_id]
    with _connect() as conn:
        _execute(
            conn,
            f"UPDATE learner_profile SET {set_clause} WHERE learner_id = ?",
            tuple(values),
        )


# ---------------------------------------------------------------------------
# Learner notes (moved from filesystem to DB)
# ---------------------------------------------------------------------------


def get_learner_notes(learner_id: str) -> str:
    """Return the learner's freeform notes markdown, or empty string."""
    with _connect() as conn:
        row = _fetchone(
            conn,
            "SELECT notes_md FROM learner_profile WHERE learner_id = ?",
            (learner_id,),
        )
        if row and row.get("notes_md"):
            return row["notes_md"]
    return ""


def save_learner_notes(learner_id: str, notes: str) -> None:
    """Save freeform notes to the DB."""
    get_or_create_learner(learner_id)
    now = datetime.now().isoformat()
    with _connect() as conn:
        _execute(
            conn,
            "UPDATE learner_profile SET notes_md = ?, updated_at = ? WHERE learner_id = ?",
            (notes, now, learner_id),
        )


# ---------------------------------------------------------------------------
# Chat log (persistent, survives restarts)
# ---------------------------------------------------------------------------


def get_chat_log(learner_id: str, persona_id: str) -> list[dict[str, str]]:
    """Return the chat log for a learner-persona pair."""
    with _connect() as conn:
        rows = _fetchall(
            conn,
            "SELECT role, content FROM chat_log "
            "WHERE learner_id = ? AND persona_id = ? "
            "ORDER BY id ASC",
            (learner_id, persona_id),
        )
        return [{"role": r["role"], "text": r["content"]} for r in rows]


def append_chat_log(learner_id: str, persona_id: str, role: str, content: str) -> None:
    """Append a message to the persistent chat log."""
    with _connect() as conn:
        _execute(
            conn,
            "INSERT INTO chat_log (learner_id, persona_id, role, content) "
            "VALUES (?, ?, ?, ?)",
            (learner_id, persona_id, role, content),
        )


# ---------------------------------------------------------------------------
# Grammar status helpers
# ---------------------------------------------------------------------------


def get_grammar_status(learner_id: str) -> dict[str, dict[str, Any]]:
    """Return dict of topic -> {status, evidence, last_tested}."""
    with _connect() as conn:
        rows = _fetchall(
            conn,
            "SELECT topic, status, evidence, last_tested "
            "FROM grammar_status WHERE learner_id = ?",
            (learner_id,),
        )
        result: dict[str, dict[str, Any]] = {}
        for row in rows:
            evidence = json.loads(row["evidence"]) if row["evidence"] else []
            result[row["topic"]] = {
                "status": row["status"],
                "evidence": evidence,
                "last_tested": row["last_tested"],
            }
        return result


def update_grammar_status(
    learner_id: str,
    topic: str,
    status: str,
    evidence_entry: str | None = None,
) -> None:
    """Update grammar topic status, appending an evidence entry."""
    get_or_create_learner(learner_id)
    now = datetime.now().isoformat()
    with _connect() as conn:
        row = _fetchone(
            conn,
            "SELECT evidence FROM grammar_status WHERE learner_id = ? AND topic = ?",
            (learner_id, topic),
        )
        if row is not None:
            evidence = json.loads(row["evidence"]) if row["evidence"] else []
        else:
            evidence = []
        if evidence_entry:
            evidence.append({"entry": evidence_entry, "at": now})
            evidence = evidence[-20:]
        evidence_json = json.dumps(evidence)

        if USE_POSTGRES:
            _execute(
                conn,
                "INSERT INTO grammar_status (learner_id, topic, status, evidence, last_tested) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT (learner_id, topic) DO UPDATE SET "
                "status = EXCLUDED.status, evidence = EXCLUDED.evidence, "
                "last_tested = EXCLUDED.last_tested",
                (learner_id, topic, status, evidence_json, now),
            )
        else:
            _execute(
                conn,
                "INSERT INTO grammar_status (learner_id, topic, status, evidence, last_tested) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(learner_id, topic) DO UPDATE SET "
                "status = excluded.status, evidence = excluded.evidence, "
                "last_tested = excluded.last_tested",
                (learner_id, topic, status, evidence_json, now),
            )


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
    with _connect() as conn:
        if USE_POSTGRES:
            _execute(
                conn,
                "INSERT INTO word_tracking "
                "(learner_id, word, translation, domain, next_review) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT (learner_id, word) DO NOTHING",
                (learner_id, word.lower().strip(), translation, domain, now),
            )
        else:
            _execute(
                conn,
                "INSERT OR IGNORE INTO word_tracking "
                "(learner_id, word, translation, domain, next_review) "
                "VALUES (?, ?, ?, ?, ?)",
                (learner_id, word.lower().strip(), translation, domain, now),
            )


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
    with _connect() as conn:
        row = _fetchone(
            conn,
            "SELECT repetitions, ease_factor, interval_days, "
            "times_correct, times_wrong "
            "FROM word_tracking WHERE learner_id = ? AND word = ?",
            (learner_id, word.lower().strip()),
        )
        if row is None:
            return

        reps = row["repetitions"]
        ef = row["ease_factor"]
        interval = row["interval_days"]
        times_correct = row["times_correct"]
        times_wrong = row["times_wrong"]

        ef = ef + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
        ef = max(1.3, ef)

        if quality < 3:
            reps = 0
            interval = 1.0
            times_wrong += 1
        else:
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

        _execute(
            conn,
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


def get_words_due(learner_id: str, limit: int = 20) -> list[dict[str, Any]]:
    """Return words where next_review <= now, oldest first."""
    now = datetime.now().isoformat()
    with _connect() as conn:
        return _fetchall(
            conn,
            "SELECT word, translation, domain, repetitions, "
            "ease_factor, interval_days, last_review, next_review, "
            "times_correct, times_wrong "
            "FROM word_tracking "
            "WHERE learner_id = ? AND (next_review IS NULL OR next_review <= ?) "
            "ORDER BY next_review ASC "
            "LIMIT ?",
            (learner_id, now, limit),
        )


def get_all_words(learner_id: str) -> list[dict[str, Any]]:
    """Return all tracked words for a learner."""
    with _connect() as conn:
        return _fetchall(
            conn,
            "SELECT word, translation, domain, repetitions, "
            "ease_factor, interval_days, last_review, next_review, "
            "times_correct, times_wrong "
            "FROM word_tracking WHERE learner_id = ? "
            "ORDER BY word ASC",
            (learner_id,),
        )


# ---------------------------------------------------------------------------
# Session log helpers
# ---------------------------------------------------------------------------


def log_message(learner_id: str, role: str, content: str) -> None:
    """Log a message to the session log."""
    with _connect() as conn:
        _execute(
            conn,
            "INSERT INTO session_log (learner_id, role, content) VALUES (?, ?, ?)",
            (learner_id, role, content),
        )


# ---------------------------------------------------------------------------
# Learner summary (for system prompt injection)
# ---------------------------------------------------------------------------


def get_learner_summary(learner_id: str) -> str:
    """Return a formatted string summarizing the learner's data."""
    with _connect() as conn:
        profile = _fetchone(
            conn,
            "SELECT * FROM learner_profile WHERE learner_id = ?",
            (learner_id,),
        )
        if profile is None:
            return ""

        parts: list[str] = []

        parts.append("## Structured learner data")
        cefr = profile.get("cefr_level") or "A1"
        parts.append(f"**CEFR level:** {cefr}")
        if profile.get("display_name"):
            parts.append(f"**Name:** {profile['display_name']}")
        if profile.get("interests"):
            try:
                interests = json.loads(profile["interests"])
                if interests:
                    parts.append(f"**Interests:** {', '.join(interests)}")
            except (json.JSONDecodeError, TypeError):
                pass

        grammar_rows = _fetchall(
            conn,
            "SELECT topic, status, last_tested "
            "FROM grammar_status WHERE learner_id = ? "
            "ORDER BY topic",
            (learner_id,),
        )
        if grammar_rows:
            status_map = {"solid": "+", "shaky": "~", "gap": "-", "untested": "?"}
            parts.append("\n**Grammar status:**")
            for row in grammar_rows:
                marker = status_map.get(row["status"], "?")
                parts.append(f"  [{marker}] {row['topic']} ({row['status']})")

        word_stats = _fetchone(
            conn,
            "SELECT COUNT(*) as total, "
            "SUM(CASE WHEN next_review <= ? THEN 1 ELSE 0 END) as due, "
            "SUM(times_correct) as total_correct, "
            "SUM(times_wrong) as total_wrong "
            "FROM word_tracking WHERE learner_id = ?",
            (datetime.now().isoformat(), learner_id),
        )
        if word_stats and word_stats["total"] and word_stats["total"] > 0:
            parts.append(
                f"\n**Vocabulary:** {word_stats['total']} words tracked, "
                f"{word_stats['due'] or 0} due for review, "
                f"{word_stats['total_correct'] or 0} correct / "
                f"{word_stats['total_wrong'] or 0} wrong lifetime"
            )
            domain_rows = _fetchall(
                conn,
                "SELECT domain, COUNT(*) as cnt "
                "FROM word_tracking "
                "WHERE learner_id = ? AND domain IS NOT NULL "
                "GROUP BY domain ORDER BY cnt DESC LIMIT 5",
                (learner_id,),
            )
            if domain_rows:
                domains = [f"{r['domain']} ({r['cnt']})" for r in domain_rows]
                parts.append(f"**Vocab domains:** {', '.join(domains)}")

        due_words = _fetchall(
            conn,
            "SELECT word, translation "
            "FROM word_tracking "
            "WHERE learner_id = ? AND (next_review IS NULL OR next_review <= ?) "
            "ORDER BY next_review ASC LIMIT 10",
            (learner_id, datetime.now().isoformat()),
        )
        if due_words:
            word_list = [f"{r['word']} ({r['translation']})" for r in due_words]
            parts.append(
                f"\n**Words due for review (weave into conversation):** "
                f"{', '.join(word_list)}"
            )

        return "\n".join(parts)
