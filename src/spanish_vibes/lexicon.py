"""Spanish ↔ English word lookup helpers with caching + AI fallback."""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any

from .db import DATA_DIR, _open_connection, now_iso
from .flow_ai import ai_available, _get_client

_DICTIONARY_PATH = DATA_DIR / "es_en_dictionary.json"
_DICTIONARY: dict[str, str] | None = None
_NORMALIZED_MAP: dict[str, str] | None = None
_WORD_RE = re.compile(r"[A-Za-zÁÉÍÓÚÜáéíóúñÑ]+", re.UNICODE)

_VERB_SUFFIXES: dict[str, tuple[str, ...]] = {
    "ar": (
        "ándonos", "ándote", "ándolo", "ándola", "ándoles", "ándolas",
        "ándonos", "ando",
        "aríamos", "aríais", "arían", "aría", "arías",
        "aremos", "aréis", "arán", "aré", "arás", "ará",
        "ábamos", "abais", "aban", "aba", "abas",
        "asteis", "aron", "é", "aste", "ó",
        "amos", "áis", "an", "o", "as", "a",
    ),
    "er": (
        "iéndonos", "iéndote", "iéndolo", "iéndola", "iéndoles", "iéndolas",
        "iendo",
        "eríamos", "eríais", "erían", "ería", "erías",
        "eremos", "eréis", "erán", "eré", "erás", "erá",
        "íamos", "íais", "ían", "ía", "ías",
        "isteis", "ieron", "í", "iste", "ió",
        "emos", "éis", "en", "o", "es", "e",
    ),
    "ir": (
        "iéndonos", "iéndote", "iéndolo", "iéndola", "iéndoles", "iéndolas",
        "iendo",
        "iríamos", "iríais", "irían", "iría", "irías",
        "iremos", "iréis", "irán", "iré", "irás", "irá",
        "íamos", "íais", "ían", "ía", "ías",
        "isteis", "ieron", "í", "iste", "ió",
        "imos", "ís", "en", "o", "es", "e",
    ),
}


def _load_dictionary() -> dict[str, str]:
    global _DICTIONARY, _NORMALIZED_MAP
    if _DICTIONARY is not None:
        return _DICTIONARY
    data: dict[str, str] = {}
    if _DICTIONARY_PATH.exists():
        try:
            data = json.loads(_DICTIONARY_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
    normalized = {}
    processed: dict[str, str] = {}
    for key, value in data.items():
        if not isinstance(key, str) or not isinstance(value, str):
            continue
        lower_key = key.strip().lower()
        if not lower_key:
            continue
        processed[lower_key] = value.strip()
        normalized[_normalize_key(lower_key)] = value.strip()
    _DICTIONARY = processed
    _NORMALIZED_MAP = normalized
    return _DICTIONARY


def _normalize_key(word: str) -> str:
    """Lowercase + strip accents for fallback lookups."""
    normalized = unicodedata.normalize("NFD", word)
    without_accents = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    return without_accents.lower()


def _clean_word(word: str) -> str:
    """Trim whitespace/punctuation while keeping internal spaces."""
    stripped = word.strip().strip("¡!¿?.,;:'\"()[]{}«»")
    stripped = re.sub(r"\s+", " ", stripped)
    return stripped


def _lemmatize_candidates(word: str) -> list[str]:
    candidates: list[str] = []
    lower = word.lower()
    for infinitive_suffix, endings in _VERB_SUFFIXES.items():
        for ending in endings:
            if lower.endswith(ending) and len(lower) > len(ending) + 1:
                base = lower[: -len(ending)]
                candidates.append(base + infinitive_suffix)
                break
    if lower.endswith("es") and len(lower) > 3:
        candidates.append(lower[:-2])
    if lower.endswith("s") and not lower.endswith("es") and len(lower) > 3:
        candidates.append(lower[:-1])
    return list(dict.fromkeys(candidates))


def lookup_local_translation(word: str) -> str | None:
    """Return translation from bundled dictionary (lemmatized if needed)."""
    dictionary = _load_dictionary()
    normalized_map = _NORMALIZED_MAP or {}
    lower = word.lower()
    if lower in dictionary:
        return dictionary[lower]
    normalized = _normalize_key(lower)
    if normalized in normalized_map:
        return normalized_map[normalized]
    for candidate in _lemmatize_candidates(lower):
        if candidate in dictionary:
            return dictionary[candidate]
        normalized_candidate = _normalize_key(candidate)
        if normalized_candidate in normalized_map:
            return normalized_map[normalized_candidate]
    return None


def _get_cached_translation(word: str) -> str | None:
    lower = word.lower()
    normalized = _normalize_key(lower)
    with _open_connection() as conn:
        row = conn.execute(
            "SELECT english_translation FROM word_translations WHERE spanish_word = ?",
            (lower,),
        ).fetchone()
        if row:
            return str(row["english_translation"])
        row = conn.execute(
            "SELECT english_translation FROM word_translations WHERE normalized_word = ?",
            (normalized,),
        ).fetchone()
        if row:
            return str(row["english_translation"])
    return None


def _store_translation(word: str, translation: str, context: str, source: str) -> None:
    lower = word.lower()
    normalized = _normalize_key(lower)
    clipped_context = context.strip()[:200]
    timestamp = now_iso()
    with _open_connection() as conn:
        conn.execute(
            """
            INSERT INTO word_translations (spanish_word, normalized_word, english_translation, context, source, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(spanish_word) DO UPDATE SET english_translation = excluded.english_translation,
                context = excluded.context,
                source = excluded.source,
                created_at = excluded.created_at
            """,
            (lower, normalized, translation, clipped_context, source, timestamp),
        )
        conn.commit()


def _translate_with_ai(word: str, context: str, *, phrase: bool = False) -> str | None:
    if not ai_available():
        return None
    client = _get_client()
    if client is None:
        return None
    safe_context = context.strip().replace("\n", " ")[:160]
    if phrase:
        prompt = (
            f"Translate the Spanish phrase '{word}' to English. "
            f"Context: '{safe_context}'. Return ONLY the English translation, up to 6 words."
        )
    else:
        prompt = (
            f"Translate the Spanish word '{word}' to English. "
            f"Context: '{safe_context}'. Return ONLY the English translation, 1-3 words max."
        )
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=20,
        )
        content = (response.choices[0].message.content or "").strip()
        # Remove quotes or punctuation wrappers
        content = content.strip("'\" ")
        return content if content else None
    except Exception:
        return None


def translate_spanish_word(word: str, context: str = "") -> dict[str, str] | None:
    """Lookup a Spanish word or phrase with cache + AI fallback."""
    cleaned = _clean_word(word)
    if not cleaned:
        return None
    is_phrase = " " in cleaned.strip()
    cached = _get_cached_translation(cleaned)
    if cached:
        return {"word": cleaned, "translation": cached, "source": "cache"}
    translation: str | None = None
    if not is_phrase:
        translation = lookup_local_translation(cleaned)
        if translation:
            _store_translation(cleaned, translation, context, source="local")
            return {"word": cleaned, "translation": translation, "source": "local"}
    translation = _translate_with_ai(cleaned, context, phrase=is_phrase)
    if translation:
        _store_translation(cleaned, translation, context, source="ai")
        return {"word": cleaned, "translation": translation, "source": "ai"}
    return None
