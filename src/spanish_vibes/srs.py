from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal, Optional

PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_ROOT.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_DB_PATH = DATA_DIR / "spanish_vibes.db"
DB_PATH = Path(os.environ.get("SPANISH_VIBES_DB_PATH", DEFAULT_DB_PATH))

DEFAULT_EASE = 2.5
MIN_EASE = 1.3
EASE_INCREMENT = 0.15
EASE_DECREMENT = 0.3
MIN_INTERVAL = 1
SRS_FAST = True


@dataclass(slots=True)
class Card:
    id: int
    front: str
    back: str
    example: str | None
    ease: float
    interval: int
    reps: int
    due_at: str
    created_at: str


def _ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _connect() -> sqlite3.Connection:
    _ensure_data_dir()
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def _row_to_card(row: Optional[sqlite3.Row]) -> Optional[Card]:
    if row is None:
        return None
    return Card(
        id=row["id"],
        front=row["front"],
        back=row["back"],
        example=row["example"],
        ease=float(row["ease"]),
        interval=int(row["interval"]),
        reps=int(row["reps"]),
        due_at=row["due_at"],
        created_at=row["created_at"],
    )


def _normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return _normalize_datetime(value).isoformat(timespec="seconds")


def init_db() -> None:
    with _connect() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS cards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                front TEXT NOT NULL,
                back TEXT NOT NULL,
                example TEXT,
                ease REAL NOT NULL,
                interval INTEGER NOT NULL,
                reps INTEGER NOT NULL,
                due_at TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.commit()


def list_cards(limit: int = 50) -> list[Card]:
    query = "SELECT * FROM cards ORDER BY created_at DESC LIMIT ?"
    with _connect() as connection:
        rows = connection.execute(query, (limit,)).fetchall()
    return [card for card in map(_row_to_card, rows) if card is not None]


def recent_cards(limit: int = 10) -> list[Card]:
    return list_cards(limit=limit)


def count_due(now: datetime) -> int:
    threshold = _iso(now)
    query = "SELECT COUNT(*) FROM cards WHERE due_at <= ?"
    with _connect() as connection:
        (count,) = connection.execute(query, (threshold,)).fetchone()
    return int(count)


def _clean(text: str | None) -> str | None:
    if text is None:
        return None
    return text.strip()


def insert_card(front: str, back: str, example: str | None = None, *, now: Optional[datetime] = None) -> Card:
    trimmed_front = _clean(front)
    trimmed_back = _clean(back)
    trimmed_example = _clean(example)
    if not trimmed_front:
        raise ValueError("front must not be empty")
    if not trimmed_back:
        raise ValueError("back must not be empty")
    timestamp = _iso(now or datetime.now(timezone.utc))
    with _connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO cards (front, back, example, ease, interval, reps, due_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (trimmed_front, trimmed_back, trimmed_example, DEFAULT_EASE, 0, 0, timestamp, timestamp),
        )
        card_id = cursor.lastrowid
        connection.commit()
    card = fetch_card(card_id)
    if card is None:  # pragma: no cover - defensive
        raise RuntimeError("Failed to read card after insert")
    return card


def fetch_card(card_id: int) -> Optional[Card]:
    query = "SELECT * FROM cards WHERE id = ?"
    with _connect() as connection:
        row = connection.execute(query, (card_id,)).fetchone()
    return _row_to_card(row)


def next_due_card(now: datetime) -> Optional[Card]:
    threshold = _iso(now)
    due_query = "SELECT * FROM cards WHERE due_at <= ? ORDER BY due_at ASC LIMIT 1"
    with _connect() as connection:
        row = connection.execute(due_query, (threshold,)).fetchone()
        if row is None:
            row = connection.execute("SELECT * FROM cards ORDER BY due_at ASC LIMIT 1").fetchone()
    return _row_to_card(row)


def schedule(card: Card, verdict: Literal["good", "again"], now: datetime) -> Card:
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
    else:  # pragma: no cover - type guard
        raise ValueError(f"Unsupported verdict: {verdict}")

    delta = timedelta(minutes=interval) if SRS_FAST else timedelta(days=interval)
    due_at = _iso(normalized_now + delta)

    with _connect() as connection:
        connection.execute(
            """
            UPDATE cards
            SET ease = ?, interval = ?, reps = ?, due_at = ?
            WHERE id = ?
            """,
            (ease, interval, reps, due_at, card.id),
        )
        connection.commit()

    updated = Card(
        id=card.id,
        front=card.front,
        back=card.back,
        example=card.example,
        ease=ease,
        interval=interval,
        reps=reps,
        due_at=due_at,
        created_at=card.created_at,
    )
    return updated


__all__ = [
    "Card",
    "SRS_FAST",
    "init_db",
    "list_cards",
    "recent_cards",
    "count_due",
    "insert_card",
    "fetch_card",
    "next_due_card",
    "schedule",
]
