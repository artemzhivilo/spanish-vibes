"""Word lifecycle helpers: seeding, intro/practice scheduling, and stats."""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from typing import Any

from .db import _open_connection, now_iso

# ── Common Spanish stop words to exclude from vocabulary harvesting ───────────
_STOP_WORDS = frozenset({
    "a", "al", "con", "de", "del", "e", "el", "en", "es", "la", "las", "lo",
    "los", "me", "mi", "muy", "no", "o", "por", "que", "se", "si", "sí",
    "su", "te", "tu", "tú", "un", "una", "y", "yo", "le", "les", "nos",
    "pero", "más", "como", "para", "sin", "ni", "ya", "ha", "he",
})


@dataclass(slots=True)
class Word:
    id: int
    spanish: str
    english: str
    emoji: str | None
    example_sentence: str | None
    concept_id: str | None
    status: str
    times_seen: int
    times_correct: int


SEED_WORDS: dict[str, list[dict[str, str]]] = {
    "greetings": [
        {"spanish": "hola", "english": "hello", "emoji": "👋", "example": "Hola, ¿cómo estás?"},
        {"spanish": "adiós", "english": "goodbye", "emoji": "👋", "example": "Adiós, nos vemos mañana."},
        {"spanish": "gracias", "english": "thank you", "emoji": "🙏", "example": "Gracias por tu ayuda."},
        {"spanish": "por favor", "english": "please", "emoji": "🙏", "example": "Por favor, pasa la sal."},
    ],
    "numbers_1_20": [
        {"spanish": "uno", "english": "one", "emoji": "1️⃣", "example": "Tengo un gato."},
        {"spanish": "dos", "english": "two", "emoji": "2️⃣", "example": "Dos libros están en la mesa."},
        {"spanish": "tres", "english": "three", "emoji": "3️⃣", "example": "Hay tres sillas aquí."},
        {"spanish": "cuatro", "english": "four", "emoji": "4️⃣", "example": "Vivimos en el cuarto piso."},
    ],
    "colors_basic": [
        {"spanish": "rojo", "english": "red", "emoji": "🔴", "example": "El coche es rojo brillante."},
        {"spanish": "azul", "english": "blue", "emoji": "🔵", "example": "El cielo está azul hoy."},
        {"spanish": "verde", "english": "green", "emoji": "🟢", "example": "Mi planta favorita es verde."},
        {"spanish": "amarillo", "english": "yellow", "emoji": "🟡", "example": "Los limones son amarillos."},
    ],
    "food_vocab": [
        {"spanish": "manzana", "english": "apple", "emoji": "🍎", "example": "Como una manzana cada mañana."},
        {"spanish": "pan", "english": "bread", "emoji": "🍞", "example": "El pan está caliente."},
        {"spanish": "queso", "english": "cheese", "emoji": "🧀", "example": "El queso es muy sabroso."},
        {"spanish": "agua", "english": "water", "emoji": "💧", "example": "Bebo agua fría."},
    ],
}


def _normalize_spanish(word: str) -> str:
    return word.strip().lower()


def seed_words() -> None:
    timestamp = now_iso()
    with _open_connection() as conn:
        for concept_id, entries in SEED_WORDS.items():
            for entry in entries:
                spanish = _normalize_spanish(entry["spanish"])
                english = entry["english"].strip()
                emoji = entry.get("emoji")
                example = entry.get("example")
                conn.execute(
                    """
                    INSERT OR IGNORE INTO words (spanish, english, emoji, example_sentence, concept_id, status, mastery_score, times_seen, times_correct, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, 'unseen', 0.0, 0, 0, ?, ?)
                    """,
                    (spanish, english, emoji, example, concept_id, timestamp, timestamp),
                )
        conn.commit()


def record_word_gap(spanish: str, english: str, concept_id: str | None) -> None:
    spanish_norm = _normalize_spanish(spanish)
    english_clean = english.strip() or english
    timestamp = now_iso()
    with _open_connection() as conn:
        row = conn.execute(
            "SELECT id, english, concept_id FROM words WHERE spanish = ?",
            (spanish_norm,),
        ).fetchone()
        if row:
            new_english = english_clean or row["english"]
            new_concept = concept_id or row["concept_id"]
            conn.execute(
                """
                UPDATE words
                SET english = ?, concept_id = COALESCE(?, concept_id), times_seen = times_seen + 1, updated_at = ?
                WHERE id = ?
                """,
                (new_english, new_concept, timestamp, row["id"]),
            )
        else:
            conn.execute(
                """
                INSERT INTO words (spanish, english, emoji, example_sentence, concept_id, status, mastery_score, times_seen, times_correct, created_at, updated_at)
                VALUES (?, ?, NULL, NULL, ?, 'unseen', 0.0, 1, 0, ?, ?)
                """,
                (spanish_norm, english_clean, concept_id, timestamp, timestamp),
            )
        conn.commit()


def record_word_tap(spanish: str, english: str | None, conversation_id: int | None, source: str = "conversation") -> None:
    timestamp = now_iso()
    spanish_norm = _normalize_spanish(spanish)
    with _open_connection() as conn:
        conn.execute(
            """
            INSERT INTO word_taps (spanish_word, english_translation, conversation_id, source, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (spanish_norm, english, conversation_id, source, timestamp),
        )
        row = conn.execute(
            "SELECT id FROM words WHERE spanish = ?",
            (spanish_norm,),
        ).fetchone()
        if row:
            conn.execute(
                "UPDATE words SET times_seen = times_seen + 1, updated_at = ? WHERE id = ?",
                (timestamp, row["id"]),
            )
        elif english:
            conn.execute(
                """
                INSERT INTO words (spanish, english, emoji, example_sentence, concept_id, status, mastery_score, times_seen, times_correct, created_at, updated_at)
                VALUES (?, ?, NULL, NULL, NULL, 'unseen', 0.0, 1, 0, ?, ?)
                """,
                (spanish_norm, english, timestamp, timestamp),
            )
        conn.commit()


def get_intro_candidate(concept_id: str) -> Word | None:
    with _open_connection() as conn:
        row = conn.execute(
            """
            SELECT * FROM words
            WHERE concept_id = ? AND status = 'unseen'
            ORDER BY created_at
            LIMIT 1
            """,
            (concept_id,),
        ).fetchone()
    if row is None:
        return None
    return _row_to_word(row)


def mark_word_introduced(word_id: int) -> None:
    timestamp = now_iso()
    with _open_connection() as conn:
        conn.execute(
            "UPDATE words SET status = 'introduced', times_seen = times_seen + 1, updated_at = ? WHERE id = ?",
            (timestamp, word_id),
        )
        conn.commit()


def get_practice_candidate(concept_id: str) -> Word | None:
    with _open_connection() as conn:
        row = conn.execute(
            """
            SELECT * FROM words
            WHERE concept_id = ? AND status IN ('introduced', 'practicing')
            ORDER BY updated_at
            LIMIT 1
            """,
            (concept_id,),
        ).fetchone()
    if row is None:
        return None
    return _row_to_word(row)


def mark_word_practice_result(word_id: int, is_correct: bool) -> None:
    timestamp = now_iso()
    with _open_connection() as conn:
        row = conn.execute("SELECT times_correct FROM words WHERE id = ?", (word_id,)).fetchone()
        current_correct = row["times_correct"] if row else 0
        new_correct = current_correct + 1 if is_correct else current_correct
        new_status = 'practicing'
        if new_correct >= 2 and is_correct:
            new_status = 'known'
        conn.execute(
            """
            UPDATE words
            SET times_seen = times_seen + 1,
                times_correct = ?,
                status = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (new_correct, new_status, timestamp, word_id),
        )
        conn.commit()


def build_practice_card(concept_id: str) -> dict[str, Any] | None:
    word = get_practice_candidate(concept_id)
    if word is None:
        return None
    sentence = _blank_sentence(word)
    options = _build_options(word)
    if len(options) < 4 or not sentence:
        return None
    prompt = "Completa la oración"
    random.shuffle(options)
    return {
        "word_id": word.id,
        "spanish": word.spanish,
        "english": word.english,
        "emoji": word.emoji,
        "sentence": sentence,
        "options": options,
        "correct_answer": word.spanish,
        "prompt": prompt,
    }


def build_match_card(concept_id: str, count: int = 4) -> dict[str, Any] | None:
    with _open_connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM words
            WHERE concept_id = ? AND status IN ('introduced', 'practicing', 'known')
            ORDER BY RANDOM()
            LIMIT ?
            """,
            (concept_id, count + 1),
        ).fetchall()
    words = [
        Word(
            id=int(row["id"]),
            spanish=row["spanish"],
            english=row["english"],
            emoji=row["emoji"],
            example_sentence=row["example_sentence"],
            concept_id=row["concept_id"],
            status=row["status"],
            times_seen=row["times_seen"],
            times_correct=row["times_correct"],
        )
        for row in rows
    ]
    if len(words) < 3:
        return None
    selected = words[: min(len(words), count)]
    english_options = [w.english for w in selected]
    random.shuffle(english_options)
    pairs = [
        {
            "word_id": w.id,
            "spanish": w.spanish,
            "english": w.english,
        }
        for w in selected
    ]
    return {
        "pairs": pairs,
        "options": english_options,
    }


def _build_options(target: Word) -> list[str]:
    needed = 3
    distractors: list[str] = []
    with _open_connection() as conn:
        rows = conn.execute(
            """
            SELECT spanish FROM words
            WHERE concept_id = ? AND id != ? AND status != 'unseen'
            ORDER BY RANDOM()
            LIMIT ?
            """,
            (target.concept_id, target.id, needed * 2),
        ).fetchall()
    for row in rows:
        spanish = row["spanish"]
        if spanish != target.spanish:
            distractors.append(spanish)
        if len(distractors) >= needed:
            break
    # fallback: use global seed entries
    if len(distractors) < needed:
        for entries in SEED_WORDS.values():
            for entry in entries:
                word = _normalize_spanish(entry["spanish"])
                if word != target.spanish and word not in distractors:
                    distractors.append(word)
                if len(distractors) >= needed:
                    break
            if len(distractors) >= needed:
                break
    return [target.spanish] + distractors[:needed]


def _blank_sentence(word: Word) -> str:
    sentence = word.example_sentence or f"___ significa '{word.english}'."
    pattern = re.compile(re.escape(word.spanish), re.IGNORECASE)
    return pattern.sub("_____", sentence, count=1)


def _row_to_word(row: Any) -> Word:
    return Word(
        id=int(row["id"]),
        spanish=str(row["spanish"]),
        english=str(row["english"]),
        emoji=row["emoji"],
        example_sentence=row["example_sentence"],
        concept_id=row["concept_id"],
        status=str(row["status"]),
        times_seen=int(row["times_seen"]),
        times_correct=int(row["times_correct"]),
    )


# ── Word tap tracking ────────────────────────────────────────────────────────


def record_word_tap(
    spanish: str,
    english: str | None = None,
    conversation_id: int | None = None,
    source: str = "conversation",
) -> None:
    """Record that the user tapped a word for translation.

    Also ensures the word exists in the words table. If it's brand-new,
    it enters as 'unseen' (the user looked it up — they don't know it yet).
    If it already exists, bump times_seen.
    """
    spanish_norm = _normalize_spanish(spanish)
    if not spanish_norm or len(spanish_norm) < 2:
        return
    timestamp = now_iso()
    with _open_connection() as conn:
        # Record the tap event (every tap, not upserted — want full history)
        conn.execute(
            """
            INSERT INTO word_taps (spanish_word, english_translation, conversation_id, source, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (spanish_norm, english, conversation_id, source, timestamp),
        )
        # Ensure word exists in words table (bump times_seen if already there)
        row = conn.execute(
            "SELECT id FROM words WHERE spanish = ?", (spanish_norm,)
        ).fetchone()
        if row:
            conn.execute(
                "UPDATE words SET times_seen = times_seen + 1, updated_at = ? WHERE id = ?",
                (timestamp, row["id"]),
            )
        elif english:
            conn.execute(
                """
                INSERT INTO words (spanish, english, emoji, example_sentence, concept_id, status, mastery_score, times_seen, times_correct, created_at, updated_at)
                VALUES (?, ?, NULL, NULL, NULL, 'unseen', 0.0, 1, 0, ?, ?)
                """,
                (spanish_norm, english.strip(), timestamp, timestamp),
            )
        conn.commit()


def get_tap_counts(limit: int = 50) -> list[dict[str, Any]]:
    """Return most-tapped words with tap counts (for analytics / prioritization)."""
    with _open_connection() as conn:
        rows = conn.execute(
            """
            SELECT spanish_word, COUNT(*) as tap_count, MAX(created_at) as last_tapped
            FROM word_taps
            GROUP BY spanish_word
            ORDER BY tap_count DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


# ── Harvest vocabulary from conversations ─────────────────────────────────────


def _extract_spanish_words(text: str) -> set[str]:
    """Extract meaningful Spanish words from text, excluding stop words."""
    # Strip punctuation, split into tokens
    cleaned = re.sub(r"[¿¡.,!?;:\"'()\[\]{}<>…—–\-/\\]", " ", text)
    tokens = cleaned.lower().split()
    words = set()
    for token in tokens:
        token = token.strip()
        if len(token) < 2:
            continue
        if token in _STOP_WORDS:
            continue
        # Skip if it looks like a number or emoji
        if re.match(r"^\d+$", token):
            continue
        # Basic check: contains at least one letter
        if not re.search(r"[a-záéíóúüñ]", token):
            continue
        words.add(token)
    return words


def harvest_conversation_words(
    user_messages: list[str],
    concept_id: str | None = None,
) -> int:
    """Extract all Spanish words from user's conversation messages and track them.

    Words the user produced correctly in conversation skip the intro card —
    they enter as 'practicing' (production evidence > recognition).

    Returns the count of newly added words.
    """
    all_words: set[str] = set()
    for msg in user_messages:
        all_words.update(_extract_spanish_words(msg))

    if not all_words:
        return 0

    timestamp = now_iso()
    new_count = 0
    with _open_connection() as conn:
        for spanish in all_words:
            row = conn.execute(
                "SELECT id, status FROM words WHERE spanish = ?", (spanish,)
            ).fetchone()
            if row:
                # Word exists — bump times_seen and times_correct (they used it!)
                conn.execute(
                    """
                    UPDATE words
                    SET times_seen = times_seen + 1,
                        times_correct = times_correct + 1,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (timestamp, row["id"]),
                )
            else:
                # New word from conversation — skip intro, enter as 'practicing'
                # We don't have the English translation yet; look it up from cache
                english = _lookup_cached_english(conn, spanish)
                if not english:
                    english = spanish  # placeholder — will get real translation on next tap
                conn.execute(
                    """
                    INSERT OR IGNORE INTO words
                    (spanish, english, emoji, example_sentence, concept_id, status,
                     mastery_score, times_seen, times_correct, created_at, updated_at)
                    VALUES (?, ?, NULL, NULL, ?, 'practicing', 0.0, 1, 1, ?, ?)
                    """,
                    (spanish, english, concept_id, timestamp, timestamp),
                )
                new_count += 1
        conn.commit()
    return new_count


def _lookup_cached_english(conn: Any, spanish: str) -> str | None:
    """Try to find an English translation from the word_translations cache."""
    row = conn.execute(
        "SELECT english_translation FROM word_translations WHERE spanish_word = ? OR normalized_word = ?",
        (spanish, spanish),
    ).fetchone()
    if row:
        return str(row["english_translation"])
    return None
