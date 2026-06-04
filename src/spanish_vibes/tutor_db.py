"""Database layer for the agent-based tutor system.

Three tables (created alongside all other app tables via db.init_db()):
  tutor_sessions      — one row per browser session
  tutor_activities    — one row per planner-issued activity
  planner_decisions   — one row per planner call (debugging / analysis)

IDs are UUIDs (TEXT) so they can be generated in Python before insertion,
matching the in-memory session_id that tutor_routes.py already uses.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from .db import _open_connection, now_iso


# ── Schema ─────────────────────────────────────────────────────────────────────


def ensure_tables() -> None:
    """Create tutor tables if they don't exist.

    Called by db.init_db() — never needs to be called directly.
    """
    with _open_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS tutor_sessions (
                id              TEXT PRIMARY KEY,
                user_id         TEXT NOT NULL,
                started_at      TEXT NOT NULL,
                ended_at        TEXT,
                planner_model   TEXT,
                session_summary TEXT
            );

            CREATE TABLE IF NOT EXISTS tutor_activities (
                id              TEXT PRIMARY KEY,
                session_id      TEXT NOT NULL,
                activity_type   TEXT NOT NULL,
                tool_params_json TEXT,
                result_json     TEXT,
                started_at      TEXT NOT NULL,
                completed_at    TEXT,
                score           REAL,
                concept_id      TEXT,
                FOREIGN KEY (session_id) REFERENCES tutor_sessions(id)
            );

            CREATE INDEX IF NOT EXISTS idx_tutor_activities_session
                ON tutor_activities(session_id);

            CREATE TABLE IF NOT EXISTS planner_decisions (
                id               TEXT PRIMARY KEY,
                session_id       TEXT NOT NULL,
                context_summary  TEXT,
                reasoning        TEXT,
                tool_name        TEXT,
                tool_params_json TEXT,
                created_at       TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES tutor_sessions(id)
            );

            CREATE INDEX IF NOT EXISTS idx_planner_decisions_session
                ON planner_decisions(session_id);
        """)
        conn.commit()


# ── Session helpers ─────────────────────────────────────────────────────────────


def create_tutor_session(
    session_id: str,
    user_id: str,
    planner_model: str | None = None,
) -> str:
    """Insert a new tutor_sessions row. Returns the session_id."""
    with _open_connection() as conn:
        conn.execute(
            """
            INSERT INTO tutor_sessions (id, user_id, started_at, planner_model)
            VALUES (?, ?, ?, ?)
            """,
            (session_id, user_id, now_iso(), planner_model),
        )
        conn.commit()
    return session_id


def get_tutor_session(session_id: str) -> dict[str, Any] | None:
    """Return a tutor_sessions row as a dict, or None if not found."""
    with _open_connection() as conn:
        row = conn.execute(
            "SELECT * FROM tutor_sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
    return dict(row) if row else None


def end_tutor_session(
    session_id: str,
    session_summary: str | None = None,
) -> None:
    """Mark a session as ended and optionally store the planner's summary."""
    with _open_connection() as conn:
        conn.execute(
            """
            UPDATE tutor_sessions
               SET ended_at = ?, session_summary = ?
             WHERE id = ?
            """,
            (now_iso(), session_summary, session_id),
        )
        conn.commit()


# ── Activity helpers ────────────────────────────────────────────────────────────


def record_tutor_activity(
    session_id: str,
    activity_type: str,
    tool_params: dict[str, Any] | None = None,
    result: dict[str, Any] | None = None,
    score: float | None = None,
    concept_id: str | None = None,
    started_at: str | None = None,
) -> str:
    """Insert a tutor_activities row. Returns the new activity id."""
    activity_id = str(uuid.uuid4())
    now = now_iso()
    with _open_connection() as conn:
        conn.execute(
            """
            INSERT INTO tutor_activities (
                id, session_id, activity_type,
                tool_params_json, result_json,
                started_at, completed_at,
                score, concept_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                activity_id,
                session_id,
                activity_type,
                json.dumps(tool_params) if tool_params else None,
                json.dumps(result) if result else None,
                started_at or now,
                now,
                score,
                concept_id,
            ),
        )
        conn.commit()
    return activity_id


# ── Planner decision log ────────────────────────────────────────────────────────


def log_planner_decision(
    session_id: str,
    tool_name: str,
    tool_params: dict[str, Any] | None = None,
    context_summary: str | None = None,
    reasoning: str | None = None,
) -> str:
    """Insert a planner_decisions row. Returns the new decision id."""
    decision_id = str(uuid.uuid4())
    with _open_connection() as conn:
        conn.execute(
            """
            INSERT INTO planner_decisions (
                id, session_id,
                context_summary, reasoning,
                tool_name, tool_params_json,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                decision_id,
                session_id,
                context_summary,
                reasoning,
                tool_name,
                json.dumps(tool_params) if tool_params else None,
                now_iso(),
            ),
        )
        conn.commit()
    return decision_id


def count_user_sessions(user_id: str) -> int:
    """Return the number of tutor sessions for a user (completed or not)."""
    with _open_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM tutor_sessions WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    return row["cnt"] if row else 0


# ── Public API ──────────────────────────────────────────────────────────────────

__all__ = [
    "ensure_tables",
    "create_tutor_session",
    "get_tutor_session",
    "end_tutor_session",
    "record_tutor_activity",
    "log_planner_decision",
    "count_user_sessions",
]
