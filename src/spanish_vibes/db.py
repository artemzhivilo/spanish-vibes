from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator, Literal, Mapping, Sequence

from .models import CardDetail, DeckSummary, LessonDeckSummary, LessonInfo

PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_ROOT.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_DB_PATH = DATA_DIR / "spanish_vibes.db"
DB_PATH = Path(os.environ.get("SPANISH_VIBES_DB_PATH", DEFAULT_DB_PATH))

DEFAULT_EASE = 2.5
DEFAULT_INTERVAL = 0
DEFAULT_REPS = 0
MIN_EASE = 1.3
EASE_INCREMENT = 0.15
EASE_DECREMENT = 0.3
MIN_INTERVAL = 1

_CARD_COLUMNS: set[str] = {
    "deck_id",
    "lesson_id",
    "kind",
    "prompt",
    "solution",
    "direction",
    "extra_json",
    "content_key",
    "ease",
    "interval",
    "reps",
    "due_at",
    "created_at",
    "updated_at",
    "concept_id",
    "variant_id",
}
_REQUIRED_CARD_COLUMNS: set[str] = {
    "deck_id",
    "lesson_id",
    "kind",
    "prompt",
    "solution",
    "content_key",
}
_VALID_CARD_KINDS: tuple[str, ...] = ("vocab", "fillblank", "verbs")
_VALID_CARD_DIRECTIONS: tuple[str, ...] = ("es_to_en", "en_to_es")


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    """Yield a SQLite connection with foreign keys enforced."""

    connection = _open_connection()
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def _open_connection() -> sqlite3.Connection:
    _ensure_data_dir()
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def now_iso(value: datetime | None = None) -> str:
    """Return the current UTC timestamp (seconds precision) as ISO 8601."""

    moment = value or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    else:
        moment = moment.astimezone(timezone.utc)
    return moment.isoformat(timespec="seconds")


def init_db() -> None:
    """Initialise the database schema if tables are missing."""

    with _open_connection() as connection:
        _create_tables(connection)
        connection.commit()


def _create_tables(connection: sqlite3.Connection) -> None:
    _drop_if_schema_mismatch(
        connection,
        "lessons",
        required={"id", "slug", "title", "level_score", "difficulty", "created_at", "updated_at"},
    )
    _drop_if_schema_mismatch(
        connection,
        "decks",
        required={"id", "lesson_id", "kind", "name"},
    )
    _drop_if_schema_mismatch(
        connection,
        "cards",
        required={
            "id",
            "deck_id",
            "lesson_id",
            "kind",
            "prompt",
            "solution",
            "content_key",
            "due_at",
            "created_at",
            "updated_at",
        },
    )

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS lessons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            level_score INTEGER NOT NULL,
            difficulty TEXT NOT NULL,
            path TEXT NOT NULL DEFAULT '',
            content_sha TEXT NOT NULL DEFAULT '',
            content_html TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS decks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lesson_id INTEGER NOT NULL,
            kind TEXT NOT NULL,
            name TEXT NOT NULL,
            UNIQUE(lesson_id, kind),
            FOREIGN KEY(lesson_id) REFERENCES lessons(id) ON DELETE CASCADE
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS cards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            deck_id INTEGER NOT NULL,
            lesson_id INTEGER NOT NULL,
            kind TEXT NOT NULL,
            prompt TEXT NOT NULL,
            solution TEXT NOT NULL,
            direction TEXT,
            extra_json TEXT NOT NULL DEFAULT '{}',
            content_key TEXT NOT NULL UNIQUE,
            ease REAL NOT NULL DEFAULT 2.5,
            interval INTEGER NOT NULL DEFAULT 0,
            reps INTEGER NOT NULL DEFAULT 0,
            due_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            concept_id TEXT,
            variant_id TEXT,
            FOREIGN KEY(deck_id) REFERENCES decks(id) ON DELETE CASCADE,
            FOREIGN KEY(lesson_id) REFERENCES lessons(id) ON DELETE CASCADE,
            CHECK(kind IN ('vocab','fillblank','verbs')),
            CHECK(direction IS NULL OR direction IN ('es_to_en','en_to_es'))
        )
        """
    )
    connection.execute("CREATE INDEX IF NOT EXISTS idx_cards_due_at ON cards(due_at)")
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_cards_lesson_kind ON cards(lesson_id, kind)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_cards_deck_kind ON cards(deck_id, kind)"
    )

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS progress (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )

    _ensure_lesson_content_columns(connection)
    _create_flow_tables(connection)


def _drop_if_schema_mismatch(connection: sqlite3.Connection, table: str, *, required: set[str]) -> None:
    if table not in _existing_tables(connection):
        return
    columns = _get_columns(connection, table)
    if not required.issubset(columns):
        connection.execute(f"DROP TABLE {table}")


def _existing_tables(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {str(row["name"]) for row in rows}


def _get_columns(connection: sqlite3.Connection, table: str) -> set[str]:
    rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(row["name"]) for row in rows}


def _ensure_lesson_content_columns(connection: sqlite3.Connection) -> None:
    columns = _get_columns(connection, "lessons")
    if "path" not in columns:
        connection.execute("ALTER TABLE lessons ADD COLUMN path TEXT NOT NULL DEFAULT ''")
    if "content_sha" not in columns:
        connection.execute("ALTER TABLE lessons ADD COLUMN content_sha TEXT NOT NULL DEFAULT ''")
    if "content_html" not in columns:
        connection.execute("ALTER TABLE lessons ADD COLUMN content_html TEXT NOT NULL DEFAULT ''")


def _create_flow_tables(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS flow_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT NOT NULL,
            ended_at TEXT,
            cards_answered INTEGER NOT NULL DEFAULT 0,
            correct_count INTEGER NOT NULL DEFAULT 0,
            flow_score REAL NOT NULL,
            xp_earned INTEGER NOT NULL DEFAULT 0,
            longest_streak INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'active'
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS flow_responses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL REFERENCES flow_sessions(id),
            card_id INTEGER REFERENCES cards(id),
            response_type TEXT NOT NULL,
            prompt_json TEXT NOT NULL,
            user_answer TEXT NOT NULL,
            expected_answer TEXT NOT NULL,
            is_correct INTEGER NOT NULL,
            response_time_ms INTEGER,
            difficulty_score REAL NOT NULL,
            flow_score_after REAL NOT NULL,
            created_at TEXT NOT NULL,
            concept_id TEXT,
            chosen_option TEXT,
            misconception_concept TEXT
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS flow_ai_cards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            card_type TEXT NOT NULL,
            base_card_id INTEGER REFERENCES cards(id),
            difficulty_score REAL NOT NULL,
            prompt TEXT NOT NULL,
            solution TEXT NOT NULL,
            extra_json TEXT NOT NULL DEFAULT '{}',
            content_hash TEXT NOT NULL UNIQUE,
            times_used INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS flow_conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL REFERENCES flow_sessions(id),
            topic TEXT NOT NULL,
            messages_json TEXT NOT NULL DEFAULT '[]',
            turn_count INTEGER NOT NULL DEFAULT 0,
            completed INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS flow_skill_profile (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lesson_id INTEGER REFERENCES lessons(id),
            card_kind TEXT NOT NULL,
            proficiency REAL NOT NULL DEFAULT 0.0,
            total_attempts INTEGER NOT NULL DEFAULT 0,
            correct_attempts INTEGER NOT NULL DEFAULT 0,
            avg_response_ms INTEGER,
            last_seen_at TEXT,
            UNIQUE(lesson_id, card_kind)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS flow_state (
            id INTEGER PRIMARY KEY DEFAULT 1,
            current_flow_score REAL NOT NULL DEFAULT 1000.0,
            total_sessions INTEGER NOT NULL DEFAULT 0,
            total_cards INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL
        )
        """
    )

    # Concept-based tables for Flow Mode v2
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS concepts (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            difficulty_level INTEGER NOT NULL DEFAULT 1,
            teach_content TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS concept_prerequisites (
            concept_id TEXT NOT NULL REFERENCES concepts(id),
            prerequisite_id TEXT NOT NULL REFERENCES concepts(id),
            PRIMARY KEY (concept_id, prerequisite_id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS concept_knowledge (
            concept_id TEXT PRIMARY KEY REFERENCES concepts(id),
            p_mastery REAL NOT NULL DEFAULT 0.0,
            n_attempts INTEGER NOT NULL DEFAULT 0,
            n_correct INTEGER NOT NULL DEFAULT 0,
            n_wrong INTEGER NOT NULL DEFAULT 0,
            teach_shown INTEGER NOT NULL DEFAULT 0,
            last_seen_at TEXT,
            updated_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS flow_mcq_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            concept_id TEXT NOT NULL REFERENCES concepts(id),
            question TEXT NOT NULL,
            correct_answer TEXT NOT NULL,
            distractors_json TEXT NOT NULL,
            difficulty INTEGER NOT NULL DEFAULT 1,
            source TEXT NOT NULL DEFAULT 'ai',
            times_used INTEGER NOT NULL DEFAULT 0,
            content_hash TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_mcq_cache_concept ON flow_mcq_cache(concept_id)"
    )

    # Ensure concept columns on flow_responses if missing
    _ensure_flow_response_concept_columns(connection)


def _ensure_flow_response_concept_columns(connection: sqlite3.Connection) -> None:
    if "flow_responses" not in _existing_tables(connection):
        return
    columns = _get_columns(connection, "flow_responses")
    if "concept_id" not in columns:
        connection.execute("ALTER TABLE flow_responses ADD COLUMN concept_id TEXT")
    if "chosen_option" not in columns:
        connection.execute("ALTER TABLE flow_responses ADD COLUMN chosen_option TEXT")
    if "misconception_concept" not in columns:
        connection.execute("ALTER TABLE flow_responses ADD COLUMN misconception_concept TEXT")


def get_or_create_lesson(slug: str, title: str, level_score: int, difficulty: str) -> int:
    """Return an existing lesson id or insert a new one."""

    timestamp = now_iso()
    with _open_connection() as connection:
        row = connection.execute(
            "SELECT id, title, level_score, difficulty FROM lessons WHERE slug = ?",
            (slug,),
        ).fetchone()
        if row:
            lesson_id = int(row["id"])
            needs_update = (
                title != row["title"]
                or level_score != row["level_score"]
                or difficulty != row["difficulty"]
            )
            if needs_update:
                connection.execute(
                    """
                    UPDATE lessons
                    SET title = ?, level_score = ?, difficulty = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (title, level_score, difficulty, timestamp, lesson_id),
                )
                connection.commit()
            return lesson_id
        cursor = connection.execute(
            """
            INSERT INTO lessons (slug, title, level_score, difficulty, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (slug, title, level_score, difficulty, timestamp, timestamp),
        )
        connection.commit()
        return int(cursor.lastrowid)


def upsert_lesson_with_content(
    *,
    slug: str,
    title: str,
    level_score: int,
    difficulty: str,
    path: str,
    content_sha: str,
    content_html: str,
) -> tuple[str, int]:
    """Insert or update lesson metadata and cached HTML content."""

    timestamp = now_iso()
    with _open_connection() as connection:
        row = connection.execute(
            "SELECT id, title, level_score, difficulty, path, content_sha FROM lessons WHERE slug = ?",
            (slug,),
        ).fetchone()
        if row:
            lesson_id = int(row["id"])
            needs_update = (
                title != row["title"]
                or level_score != row["level_score"]
                or difficulty != row["difficulty"]
                or path != row["path"]
                or content_sha != row["content_sha"]
            )
            if needs_update:
                connection.execute(
                    """
                    UPDATE lessons
                    SET title = ?, level_score = ?, difficulty = ?, path = ?, content_sha = ?, content_html = ?, updated_at = ?
                    WHERE slug = ?
                    """,
                    (title, level_score, difficulty, path, content_sha, content_html, timestamp, slug),
                )
                connection.commit()
                return "updated", lesson_id
            return "unchanged", lesson_id

        cursor = connection.execute(
            """
            INSERT INTO lessons (
                slug, title, level_score, difficulty, path, content_sha, content_html, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (slug, title, level_score, difficulty, path, content_sha, content_html, timestamp, timestamp),
        )
        connection.commit()
        return "inserted", int(cursor.lastrowid)


def get_or_create_deck(lesson_id: int, kind: str, name: str) -> int:
    """Return deck id for the provided lesson/kind combination."""

    normalized_kind = kind.strip().lower()
    if normalized_kind not in _VALID_CARD_KINDS:
        raise ValueError(f"Unsupported deck kind: {kind}")
    clean_name = name.strip()
    if not clean_name:
        raise ValueError("Deck name must not be empty")

    with _open_connection() as connection:
        row = connection.execute(
            "SELECT id, name FROM decks WHERE lesson_id = ? AND kind = ?",
            (lesson_id, normalized_kind),
        ).fetchone()
        if row:
            deck_id = int(row["id"])
            if clean_name != row["name"]:
                connection.execute(
                    "UPDATE decks SET name = ? WHERE id = ?",
                    (clean_name, deck_id),
                )
                connection.commit()
            return deck_id
        cursor = connection.execute(
            """
            INSERT INTO decks (lesson_id, kind, name)
            VALUES (?, ?, ?)
            """,
            (lesson_id, normalized_kind, clean_name),
        )
        connection.commit()
        return int(cursor.lastrowid)


def upsert_card_by_key(fields: Mapping[str, Any]) -> tuple[Literal["inserted", "updated"], int]:
    """Insert or update a card based on its unique content key."""

    if "content_key" not in fields:
        raise ValueError("fields must include a content_key")

    record = _sanitise_card_fields(fields)
    now = now_iso()
    record.setdefault("extra_json", "{}")
    record.setdefault("ease", DEFAULT_EASE)
    record.setdefault("interval", DEFAULT_INTERVAL)
    record.setdefault("reps", DEFAULT_REPS)
    record.setdefault("due_at", now)
    record.setdefault("created_at", now)
    record["updated_at"] = record.get("updated_at") or now

    missing = _REQUIRED_CARD_COLUMNS - record.keys()
    if missing:
        missing_keys = ", ".join(sorted(missing))
        raise ValueError(f"Missing required card fields: {missing_keys}")

    normalized_kind = str(record["kind"]).strip().lower()
    if normalized_kind not in _VALID_CARD_KINDS:
        raise ValueError(f"Unsupported card kind: {record['kind']}")
    record["kind"] = normalized_kind

    direction = record.get("direction")
    if direction is not None:
        normalized_direction = str(direction).strip().lower()
        if normalized_direction not in _VALID_CARD_DIRECTIONS:
            raise ValueError(f"Unsupported card direction: {direction}")
        record["direction"] = normalized_direction

    with _open_connection() as connection:
        existing = connection.execute(
            "SELECT id, created_at FROM cards WHERE content_key = ?",
            (record["content_key"],),
        ).fetchone()
        if existing:
            card_id = int(existing["id"])
            persisted_created_at = existing["created_at"]
            record.setdefault("created_at", persisted_created_at)
            update_fields = {k: v for k, v in record.items() if k != "created_at"}
            assignments = ", ".join(f"{column} = ?" for column in update_fields)
            params = list(update_fields.values())
            params.append(card_id)
            connection.execute(
                f"UPDATE cards SET {assignments} WHERE id = ?",
                params,
            )
            connection.commit()
            return "updated", card_id

        columns = ", ".join(record.keys())
        placeholders = ", ".join("?" for _ in record)
        cursor = connection.execute(
            f"INSERT INTO cards ({columns}) VALUES ({placeholders})",
            tuple(record.values()),
        )
        connection.commit()
        return "inserted", int(cursor.lastrowid)


def _sanitise_card_fields(fields: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in fields.items() if key in _CARD_COLUMNS}


def due_now_clause(column: str = "due_at") -> str:
    """Return a SQL snippet to filter cards that are due now or earlier."""

    return f"{column} <= ?"


def fetch_lesson_deck_summaries(now: datetime | None = None) -> list[LessonDeckSummary]:
    """Return per-lesson deck summaries with card counts and due totals."""

    reference = now_iso(now)
    query = (
        """
        SELECT
            l.id AS lesson_id,
            l.slug AS lesson_slug,
            l.title AS lesson_title,
            l.level_score AS lesson_level_score,
            l.difficulty AS lesson_difficulty,
            d.id AS deck_id,
            d.name AS deck_name,
            d.kind AS deck_kind,
            COUNT(c.id) AS card_count,
            COALESCE(SUM(CASE WHEN c.due_at <= :now THEN 1 ELSE 0 END), 0) AS due_count
        FROM lessons l
        JOIN decks d ON d.lesson_id = l.id
        LEFT JOIN cards c ON c.deck_id = d.id
        GROUP BY l.id, d.id
        ORDER BY l.level_score ASC, l.slug ASC, d.kind ASC, d.name ASC
        """
    )

    summaries: dict[int, LessonDeckSummary] = {}
    with _open_connection() as connection:
        rows = connection.execute(query, {"now": reference}).fetchall()

    for row in rows:
        lesson_id = int(row["lesson_id"])
        deck_summary = DeckSummary(
            id=int(row["deck_id"]),
            lesson_id=lesson_id,
            name=str(row["deck_name"]),
            kind=str(row["deck_kind"]),
            card_count=int(row["card_count"] or 0),
            due_count=int(row["due_count"] or 0),
        )

        lesson = summaries.get(lesson_id)
        if lesson is None:
            lesson = LessonDeckSummary(
                id=lesson_id,
                slug=str(row["lesson_slug"]),
                title=str(row["lesson_title"]),
                level_score=int(row["lesson_level_score"] or 0),
                difficulty=str(row["lesson_difficulty"]),
                total_cards=0,
                due_cards=0,
                decks=[],
            )
            summaries[lesson_id] = lesson

        lesson.decks.append(deck_summary)
        lesson.total_cards += deck_summary.card_count
        lesson.due_cards += deck_summary.due_count

    ordered = sorted(
        summaries.values(),
        key=lambda item: (item.level_score, item.slug),
    )
    return ordered


def fetch_decks(
    *,
    kind: str | None = None,
    deck_ids: Sequence[int] | None = None,
    now: datetime | None = None,
) -> list[DeckSummary]:
    """Return deck summaries filtered by kind or id."""

    reference = now_iso(now)
    clauses: list[str] = []
    params: list[Any] = []

    if kind:
        clauses.append("d.kind = ?")
        params.append(kind)

    if deck_ids:
        placeholders = ",".join("?" for _ in deck_ids)
        clauses.append(f"d.id IN ({placeholders})")
        params.extend(deck_ids)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    query = (
        """
        SELECT
            d.id,
            d.lesson_id,
            d.name,
            d.kind,
            COUNT(c.id) AS card_count,
            COALESCE(SUM(CASE WHEN c.due_at <= ? THEN 1 ELSE 0 END), 0) AS due_count
        FROM decks d
        LEFT JOIN cards c ON c.deck_id = d.id
        {where}
        GROUP BY d.id
        ORDER BY d.kind ASC, d.name ASC
        """
    ).format(where=where)

    rows: list[sqlite3.Row]
    with _open_connection() as connection:
        rows = connection.execute(query, [reference, *params]).fetchall()

    return [
        DeckSummary(
            id=int(row["id"]),
            lesson_id=int(row["lesson_id"]),
            name=str(row["name"]),
            kind=str(row["kind"]),
            card_count=int(row["card_count"] or 0),
            due_count=int(row["due_count"] or 0),
        )
        for row in rows
    ]


def count_due_cards(
    now: datetime,
    *,
    deck_ids: Sequence[int] | None = None,
    kind: str | None = None,
) -> int:
    """Count cards due at or before the provided time."""

    query = "SELECT COUNT(*) FROM cards WHERE due_at <= ?"
    params: list[Any] = [now_iso(now)]

    if deck_ids:
        placeholders = ",".join("?" for _ in deck_ids)
        query += f" AND deck_id IN ({placeholders})"
        params.extend(deck_ids)

    if kind:
        query += " AND kind = ?"
        params.append(kind)

    with _open_connection() as connection:
        (count,) = connection.execute(query, params).fetchone()
    return int(count)


def fetch_card_detail(card_id: int) -> CardDetail | None:
    """Return card detail for the given id."""

    with _open_connection() as connection:
        row = connection.execute("SELECT * FROM cards WHERE id = ?", (card_id,)).fetchone()
    return _row_to_card_detail(row)


def get_lesson_by_slug(slug: str) -> dict[str, Any] | None:
    with _open_connection() as connection:
        row = connection.execute("SELECT * FROM lessons WHERE slug = ?", (slug,)).fetchone()
    return dict(row) if row else None


def update_lesson_cache(
    slug: str,
    *,
    content_sha: str,
    content_html: str,
    path: str | None = None,
) -> None:
    timestamp = now_iso()
    assignments = ["content_sha = ?", "content_html = ?", "updated_at = ?"]
    params: list[Any] = [content_sha, content_html, timestamp, slug]
    if path is not None:
        assignments.insert(0, "path = ?")
        params.insert(0, path)
    with _open_connection() as connection:
        connection.execute(
            f"UPDATE lessons SET {', '.join(assignments)} WHERE slug = ?",
            params,
        )
        connection.commit()


def fetch_next_due_card(
    now: datetime,
    *,
    deck_ids: Sequence[int],
    kind: str | None = None,
) -> CardDetail | None:
    """Return the earliest due card for the provided decks/kind, falling back to next upcoming."""

    if not deck_ids:
        return None

    due_params: list[Any] = list(deck_ids)
    upcoming_params: list[Any] = list(deck_ids)

    placeholders = ",".join("?" for _ in deck_ids)
    kind_clause = ""
    if kind:
        kind_clause = " AND kind = ?"
        due_params.append(kind)
        upcoming_params.append(kind)

    due_params.append(now_iso(now))
    due_query = (
        f"SELECT * FROM cards WHERE deck_id IN ({placeholders})"
        f"{kind_clause} AND due_at <= ? ORDER BY due_at ASC LIMIT 1"
    )

    with _open_connection() as connection:
        row = connection.execute(due_query, due_params).fetchone()
        if row is None:
            upcoming_query = (
                f"SELECT * FROM cards WHERE deck_id IN ({placeholders})"
                f"{kind_clause} ORDER BY due_at ASC LIMIT 1"
            )
            row = connection.execute(upcoming_query, upcoming_params).fetchone()
    return _row_to_card_detail(row)


def update_card_schedule(
    card: CardDetail,
    verdict: Literal["good", "again"],
    now: datetime,
    *,
    fast_mode: bool = True,
) -> CardDetail:
    """Update scheduling metadata for a card and return the refreshed record."""

    normalized_now = _normalize_datetime(now)

    if verdict == "again":
        ease = max(MIN_EASE, card.ease - EASE_DECREMENT)
        reps = 0
        interval = MIN_INTERVAL
    elif verdict == "good":
        ease = card.ease + EASE_INCREMENT
        reps = card.reps + 1
        base_interval = card.interval if card.interval > 0 else MIN_INTERVAL
        interval = max(MIN_INTERVAL, int(round(base_interval * ease)))
    else:  # pragma: no cover - defensive guard
        raise ValueError(f"Unsupported verdict: {verdict}")

    delta = timedelta(minutes=interval) if fast_mode else timedelta(days=interval)
    due_at = _normalize_datetime(normalized_now + delta)
    due_iso = due_at.isoformat(timespec="seconds")
    updated_at = normalized_now.isoformat(timespec="seconds")

    with _open_connection() as connection:
        connection.execute(
            """
            UPDATE cards
            SET ease = ?, interval = ?, reps = ?, due_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (ease, interval, reps, due_iso, updated_at, card.id),
        )
        connection.commit()

    return replace(
        card,
        ease=ease,
        interval=interval,
        reps=reps,
        due_at=due_iso,
        updated_at=updated_at,
    )


def _row_to_card_detail(row: sqlite3.Row | None) -> CardDetail | None:
    if row is None:
        return None
    extra_raw = row["extra_json"] or "{}"
    try:
        extra = json.loads(extra_raw)
    except json.JSONDecodeError:  # pragma: no cover - defensive
        extra = {}
    direction = row["direction"]
    return CardDetail(
        id=int(row["id"]),
        deck_id=int(row["deck_id"]),
        lesson_id=int(row["lesson_id"]),
        kind=str(row["kind"]),
        prompt=str(row["prompt"]),
        solution=str(row["solution"]),
        direction=str(direction) if direction is not None else None,
        extra=extra,
        ease=float(row["ease"]),
        interval=int(row["interval"]),
        reps=int(row["reps"]),
        due_at=str(row["due_at"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        concept_id=str(row["concept_id"]) if row["concept_id"] is not None else None,
        variant_id=str(row["variant_id"]) if row["variant_id"] is not None else None,
    )


def _normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def fetch_lesson_by_slug(slug: str) -> LessonInfo | None:
    row = get_lesson_by_slug(slug)
    if row is None:
        return None
    return LessonInfo(
        id=int(row["id"]),
        slug=str(row["slug"]),
        title=str(row["title"]),
        level_score=int(row.get("level_score", 0) or 0),
        difficulty=str(row.get("difficulty", "")),
    )


def fetch_cards_for_deck(deck_id: int, *, limit: int | None = None) -> list[CardDetail]:
    query = "SELECT * FROM cards WHERE deck_id = ? ORDER BY created_at ASC"
    params: list[Any] = [deck_id]
    if limit is not None:
        query += " LIMIT ?"
        params.append(limit)
    with _open_connection() as connection:
        rows = connection.execute(query, params).fetchall()
    cards = [_row_to_card_detail(row) for row in rows]
    return [card for card in cards if card is not None]


def get_progress(key: str, default: str = "0") -> str:
    with _open_connection() as connection:
        row = connection.execute(
            "SELECT value FROM progress WHERE key = ?", (key,)
        ).fetchone()
    return str(row["value"]) if row else default


def set_progress(key: str, value: str) -> None:
    timestamp = now_iso()
    with _open_connection() as connection:
        connection.execute(
            """
            INSERT INTO progress (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
            """,
            (key, value, timestamp),
        )
        connection.commit()


def get_xp() -> int:
    return int(get_progress("xp", "0"))


def add_xp(amount: int) -> int:
    current = get_xp()
    new_total = current + amount
    set_progress("xp", str(new_total))
    return new_total


def get_streak() -> tuple[int, str]:
    count = int(get_progress("streak_count", "0"))
    last_date = get_progress("streak_last_date", "")
    return count, last_date


def record_practice_today(today_iso: str) -> int:
    count, last_date = get_streak()
    if last_date == today_iso:
        return count
    from datetime import date

    today = date.fromisoformat(today_iso)
    if last_date:
        last = date.fromisoformat(last_date)
        delta = (today - last).days
        if delta == 1:
            count += 1
        elif delta > 1:
            count = 1
    else:
        count = 1
    set_progress("streak_count", str(count))
    set_progress("streak_last_date", today_iso)
    return count


def fetch_all_lesson_slugs() -> list[str]:
    """Return all lesson slugs ordered by chapter/lesson number."""
    with _open_connection() as connection:
        rows = connection.execute("SELECT slug FROM lessons ORDER BY slug").fetchall()
    return [row["slug"] for row in rows]


def fetch_lesson_mastery() -> dict[int, dict[str, int]]:
    query = """
        SELECT
            lesson_id,
            COUNT(*) AS total,
            COALESCE(SUM(CASE WHEN reps >= 5 THEN 1 ELSE 0 END), 0) AS mastered,
            COALESCE(SUM(CASE WHEN reps >= 2 AND reps < 5 THEN 1 ELSE 0 END), 0) AS familiar,
            COALESCE(SUM(CASE WHEN reps >= 1 AND reps < 2 THEN 1 ELSE 0 END), 0) AS learning,
            COALESCE(SUM(CASE WHEN reps == 0 THEN 1 ELSE 0 END), 0) AS new
        FROM cards
        GROUP BY lesson_id
    """
    with _open_connection() as connection:
        rows = connection.execute(query).fetchall()
    result: dict[int, dict[str, int]] = {}
    for row in rows:
        result[int(row["lesson_id"])] = {
            "total": int(row["total"]),
            "mastered": int(row["mastered"]),
            "familiar": int(row["familiar"]),
            "learning": int(row["learning"]),
            "new": int(row["new"]),
        }
    return result


__all__ = [
    "connect",
    "DB_PATH",
    "DEFAULT_DB_PATH",
    "DEFAULT_EASE",
    "due_now_clause",
    "fetch_lesson_deck_summaries",
    "fetch_decks",
    "count_due_cards",
    "fetch_card_detail",
    "fetch_next_due_card",
    "fetch_lesson_by_slug",
    "fetch_cards_for_deck",
    "update_card_schedule",
    "upsert_lesson_with_content",
    "get_lesson_by_slug",
    "update_lesson_cache",
    "get_or_create_deck",
    "get_or_create_lesson",
    "init_db",
    "now_iso",
    "upsert_card_by_key",
    "get_progress",
    "set_progress",
    "get_xp",
    "add_xp",
    "get_streak",
    "record_practice_today",
    "fetch_lesson_mastery",
]
