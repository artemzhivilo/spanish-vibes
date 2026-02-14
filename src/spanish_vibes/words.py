"""Word lifecycle helpers: seeding, intro/practice scheduling, and stats."""

from __future__ import annotations

import json
import random
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .db import _open_connection, now_iso

# ── Common Spanish stop words to exclude from vocabulary harvesting ───────────
_STOP_WORDS = frozenset({
    "a", "al", "con", "de", "del", "e", "el", "en", "es", "la", "las", "lo",
    "los", "me", "mi", "muy", "no", "o", "por", "que", "se", "si", "sí",
    "su", "te", "tu", "tú", "un", "una", "y", "yo", "le", "les", "nos",
    "pero", "más", "como", "para", "sin", "ni", "ya", "ha", "he",
})

_GRAMMAR_CONCEPTS = frozenset({
    "subject_pronouns", "nouns_gender", "articles_definite", "articles_indefinite",
    "ser_present", "estar_present", "tener_present", "hay", "plurals",
    "possessive_adjectives", "demonstratives", "basic_questions",
    "adjective_agreement", "negation", "muy_mucho",
    "present_tense_ar", "present_tense_er_ir", "basic_prepositions",
    "telling_time", "frequency_adverbs", "ir_a", "gustar", "querer",
    "describing_people", "ordering_food", "asking_directions", "daily_routine",
    "tener_que_hay_que", "estar_gerund", "poder_infinitive", "conjunctions",
    "reflexive_verbs", "direct_object_pronouns", "indirect_object_pronouns",
    "comparatives", "present_perfect", "preterite_regular", "preterite_irregular",
    "imperfect_intro", "por_vs_para", "conditional_politeness", "imperative_basic",
})

SEED_WORDS_PATH = Path(__file__).resolve().parents[2] / "data" / "seed_words.json"
FILL_BLANKS_PATH = Path(__file__).resolve().parents[2] / "data" / "fill_blanks.json"
_FILL_BLANKS_CACHE: dict[str, list[dict[str, Any]]] | None = None


@dataclass(slots=True)
class Word:
    id: int
    spanish: str
    english: str
    emoji: str | None
    example_sentence: str | None
    concept_id: str | None
    topic_slug: str | None
    status: str
    times_seen: int
    times_correct: int


def _normalize_spanish(word: str) -> str:
    return word.strip().lower()


def seed_words() -> int:
    """Seed words from data/seed_words.json. Returns count inserted."""
    if not SEED_WORDS_PATH.exists():
        return 0
    try:
        all_words = json.loads(SEED_WORDS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return 0
    if not isinstance(all_words, dict):
        return 0

    timestamp = now_iso()
    seeded = 0
    with _open_connection() as conn:
        for concept_id, entries in all_words.items():
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                spanish = _normalize_spanish(str(entry.get("spanish", "")))
                english = str(entry.get("english", "")).strip()
                if not spanish or not english:
                    continue
                emoji = entry.get("emoji")
                example = entry.get("example")
                topic_slug = entry.get("topic_slug")
                initial_status = "introduced" if concept_id in _GRAMMAR_CONCEPTS else "unseen"
                result = conn.execute(
                    """
                    INSERT OR IGNORE INTO words
                    (spanish, english, emoji, example_sentence, concept_id, topic_slug, status, mastery_score, times_seen, times_correct, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 0.0, 0, 0, ?, ?)
                    """,
                    (spanish, english, emoji, example, concept_id, topic_slug, initial_status, timestamp, timestamp),
                )
                if result.rowcount and int(result.rowcount) > 0:
                    seeded += 1
        for grammar_concept_id in _GRAMMAR_CONCEPTS:
            conn.execute(
                """
                UPDATE words
                SET status = 'introduced', updated_at = ?
                WHERE concept_id = ? AND status = 'unseen'
                """,
                (timestamp, grammar_concept_id),
            )
        conn.commit()
    return seeded


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
                INSERT INTO words (spanish, english, emoji, example_sentence, concept_id, topic_slug, status, mastery_score, times_seen, times_correct, created_at, updated_at)
                VALUES (?, ?, NULL, NULL, ?, ?, 'unseen', 0.0, 1, 0, ?, ?)
                """,
                (spanish_norm, english_clean, concept_id, _topic_slug_for_concept(concept_id), timestamp, timestamp),
            )
        conn.commit()


def record_word_tap(
    spanish: str,
    english: str | None = None,
    conversation_id: int | None = None,
    source: str = "conversation",
) -> None:
    """Record that the user tapped a word for translation."""
    spanish_norm = _normalize_spanish(spanish)
    if not spanish_norm or len(spanish_norm) < 2:
        return
    timestamp = now_iso()
    with _open_connection() as conn:
        conn.execute(
            """
            INSERT INTO word_taps (spanish_word, english_translation, conversation_id, source, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (spanish_norm, english, conversation_id, source, timestamp),
        )
        row = conn.execute("SELECT id FROM words WHERE spanish = ?", (spanish_norm,)).fetchone()
        if row:
            conn.execute(
                "UPDATE words SET times_seen = times_seen + 1, updated_at = ? WHERE id = ?",
                (timestamp, row["id"]),
            )
        elif english:
            conn.execute(
                """
                INSERT INTO words (spanish, english, emoji, example_sentence, concept_id, topic_slug, status, mastery_score, times_seen, times_correct, created_at, updated_at)
                VALUES (?, ?, NULL, NULL, NULL, NULL, 'unseen', 0.0, 1, 0, ?, ?)
                """,
                (spanish_norm, english.strip(), timestamp, timestamp),
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
    return _row_to_word(row) if row is not None else None


def get_intro_candidate_weighted(
    concept_id: str,
    top_interest_slugs: list[str] | None = None,
) -> Word | None:
    """Pick unseen word, preferring high-interest topic slugs."""
    with _open_connection() as conn:
        if top_interest_slugs:
            cleaned = [slug.strip().lower() for slug in top_interest_slugs if slug and slug.strip()]
            if cleaned:
                placeholders = ",".join("?" for _ in cleaned)
                row = conn.execute(
                    f"""
                    SELECT * FROM words
                    WHERE concept_id = ? AND status = 'unseen' AND LOWER(COALESCE(topic_slug, '')) IN ({placeholders})
                    ORDER BY created_at
                    LIMIT 1
                    """,
                    (concept_id, *cleaned),
                ).fetchone()
                if row is not None:
                    return _row_to_word(row)
        row = conn.execute(
            """
            SELECT * FROM words
            WHERE concept_id = ? AND status = 'unseen'
            ORDER BY created_at
            LIMIT 1
            """,
            (concept_id,),
        ).fetchone()
    return _row_to_word(row) if row is not None else None


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
    return _row_to_word(row) if row is not None else None


def mark_word_practice_result(word_id: int, is_correct: bool) -> None:
    timestamp = now_iso()
    with _open_connection() as conn:
        row = conn.execute("SELECT times_correct FROM words WHERE id = ?", (word_id,)).fetchone()
        current_correct = int(row["times_correct"]) if row else 0
        new_correct = current_correct + 1 if is_correct else current_correct
        new_status = "practicing"
        if new_correct >= 2 and is_correct:
            new_status = "known"
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
    words = [_row_to_word(row) for row in rows]
    if len(words) < 3:
        return None
    selected = words[: min(len(words), count)]
    english_options = [w.english for w in selected]
    random.shuffle(english_options)
    pairs = [{"word_id": w.id, "spanish": w.spanish, "english": w.english} for w in selected]
    return {"pairs": pairs, "options": english_options}


def build_sentence_builder_card(concept_id: str) -> dict[str, Any] | None:
    """Build a sentence builder card from example sentences in words table."""
    with _open_connection() as conn:
        rows = conn.execute(
            """
            SELECT example_sentence FROM words
            WHERE concept_id = ? AND example_sentence IS NOT NULL AND example_sentence != ''
            ORDER BY RANDOM()
            LIMIT 8
            """,
            (concept_id,),
        ).fetchall()

    for row in rows:
        sentence = str(row["example_sentence"]).strip()
        if not sentence:
            continue
        clean = sentence.rstrip(".!?¡¿").strip()
        words = [w for w in clean.split() if w]
        if not (3 <= len(words) <= 8):
            continue
        punctuation = sentence[-1] if sentence and sentence[-1] in ".!?" else "."
        scrambled = words[:]
        for _ in range(20):
            random.shuffle(scrambled)
            if scrambled != words:
                break
        if scrambled == words:
            continue
        return {
            "correct_words": words,
            "scrambled_words": scrambled,
            "punctuation": punctuation,
            "correct_sentence": " ".join(words) + punctuation,
        }
    return None


def build_emoji_card(concept_id: str) -> dict[str, Any] | None:
    """Build emoji association card with one target and three distractors."""
    with _open_connection() as conn:
        target_rows = conn.execute(
            """
            SELECT * FROM words
            WHERE concept_id = ? AND emoji IS NOT NULL AND emoji != ''
              AND status IN ('introduced', 'practicing', 'known')
            ORDER BY RANDOM()
            LIMIT 1
            """,
            (concept_id,),
        ).fetchall()
        if not target_rows:
            return None
        target = target_rows[0]

        distractors = conn.execute(
            """
            SELECT spanish FROM words
            WHERE id != ? AND emoji IS NOT NULL AND emoji != ''
              AND status IN ('introduced', 'practicing', 'known')
            ORDER BY RANDOM()
            LIMIT 12
            """,
            (target["id"],),
        ).fetchall()

    unique_distractors: list[str] = []
    for row in distractors:
        candidate = str(row["spanish"])
        if candidate == str(target["spanish"]) or candidate in unique_distractors:
            continue
        unique_distractors.append(candidate)
        if len(unique_distractors) >= 3:
            break
    if len(unique_distractors) < 3:
        return None

    options = [str(target["spanish"]), *unique_distractors]
    random.shuffle(options)
    return {
        "word_id": int(target["id"]),
        "emoji": target["emoji"],
        "correct_spanish": str(target["spanish"]),
        "english_hint": str(target["english"]),
        "options": options,
    }


def _load_fill_blanks() -> dict[str, list[dict[str, Any]]]:
    global _FILL_BLANKS_CACHE
    if _FILL_BLANKS_CACHE is None:
        if FILL_BLANKS_PATH.exists():
            try:
                loaded = json.loads(FILL_BLANKS_PATH.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    _FILL_BLANKS_CACHE = loaded
                else:
                    _FILL_BLANKS_CACHE = {}
            except Exception:
                _FILL_BLANKS_CACHE = {}
        else:
            _FILL_BLANKS_CACHE = {}
    return _FILL_BLANKS_CACHE


def build_fill_blank_card(concept_id: str) -> dict[str, Any] | None:
    """Build grammar fill-in-the-blank card from pre-authored items."""
    blanks = _load_fill_blanks()
    items = blanks.get(concept_id, [])
    if not items:
        return None
    item = random.choice(items)
    answer = str(item.get("answer", "")).strip()
    sentence = str(item.get("sentence", "")).strip()
    distractors = item.get("distractors", [])
    if not answer or not sentence or not isinstance(distractors, list):
        return None
    clean_distractors = [str(d).strip() for d in distractors if str(d).strip() and str(d).strip() != answer]
    clean_distractors = clean_distractors[:3]
    if len(clean_distractors) < 3:
        return None
    options = [answer, *clean_distractors]
    random.shuffle(options)
    return {
        "sentence": sentence,
        "correct_answer": answer,
        "options": options,
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
        spanish = str(row["spanish"])
        if spanish != target.spanish:
            distractors.append(spanish)
        if len(distractors) >= needed:
            break

    if len(distractors) < needed:
        with _open_connection() as conn:
            rows = conn.execute(
                "SELECT spanish FROM words WHERE id != ? ORDER BY RANDOM() LIMIT ?",
                (target.id, needed * 6),
            ).fetchall()
        for row in rows:
            spanish = _normalize_spanish(str(row["spanish"]))
            if spanish != target.spanish and spanish not in distractors:
                distractors.append(spanish)
            if len(distractors) >= needed:
                break

    return [target.spanish] + distractors[:needed]


def _blank_sentence(word: Word) -> str:
    sentence = word.example_sentence or f"_____ significa '{word.english}'."
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
        topic_slug=row["topic_slug"] if "topic_slug" in row.keys() else None,
        status=str(row["status"]),
        times_seen=int(row["times_seen"]),
        times_correct=int(row["times_correct"]),
    )


def get_tap_counts(limit: int = 50) -> list[dict[str, Any]]:
    """Return most-tapped words with tap counts."""
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
    cleaned = re.sub(r"[¿¡.,!?;:\"'()\[\]{}<>…—–\-/\\]", " ", text)
    tokens = cleaned.lower().split()
    words = set()
    for token in tokens:
        token = token.strip()
        if len(token) < 2:
            continue
        if token in _STOP_WORDS:
            continue
        if re.match(r"^\d+$", token):
            continue
        if not re.search(r"[a-záéíóúüñ]", token):
            continue
        words.add(token)
    return words


def harvest_conversation_words(
    user_messages: list[str],
    concept_id: str | None = None,
) -> int:
    """Extract words from user conversation and track them."""
    all_words: set[str] = set()
    for msg in user_messages:
        all_words.update(_extract_spanish_words(msg))

    if not all_words:
        return 0

    timestamp = now_iso()
    new_count = 0
    topic_slug = _topic_slug_for_concept(concept_id)
    with _open_connection() as conn:
        for spanish in all_words:
            row = conn.execute(
                "SELECT id FROM words WHERE spanish = ?", (spanish,)
            ).fetchone()
            if row:
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
                english = _lookup_cached_english(conn, spanish) or spanish
                conn.execute(
                    """
                    INSERT OR IGNORE INTO words
                    (spanish, english, emoji, example_sentence, concept_id, topic_slug, status,
                     mastery_score, times_seen, times_correct, created_at, updated_at)
                    VALUES (?, ?, NULL, NULL, ?, ?, 'practicing', 0.0, 1, 1, ?, ?)
                    """,
                    (spanish, english, concept_id, topic_slug, timestamp, timestamp),
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


def _topic_slug_for_concept(concept_id: str | None) -> str | None:
    if not concept_id:
        return None
    try:
        from .interest import CONCEPT_TOPIC_MAP
    except Exception:
        return None
    return CONCEPT_TOPIC_MAP.get(concept_id)
