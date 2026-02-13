from __future__ import annotations

import argparse
import json
import re
import unicodedata
from dataclasses import dataclass
from hashlib import sha1
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

import yaml

from .db import get_or_create_deck, get_or_create_lesson, init_db, now_iso, upsert_card_by_key
from .models import (
    CARD_KINDS,
    CardRecord,
    LessonConcept,
    LessonConceptExample,
    LessonDoc,
    LessonExercise,
    LessonExerciseFeedback,
    LessonFillBlankEntry,
    LessonVocabularyEntry,
)

FRONT_MATTER_DELIMITER = "---"
_VALID_DECK_KINDS: set[str] = set(CARD_KINDS)

_DECK_LABELS: dict[str, str] = {
    "vocab": "Vocabulary",
    "fillblank": "Fill in the Blank",
    "verbs": "Verb Drills",
}


@dataclass(slots=True)
class LessonParseResult:
    doc: LessonDoc
    decks: tuple[str, ...]
    front_matter: dict[str, Any]
    source_path: Path
    raw_text: str
    body_markdown: str


class LessonParseError(RuntimeError):
    pass


def load_lesson(path: Path) -> LessonParseResult:
    """Parse a markdown lesson file into a LessonDoc with metadata."""

    text = path.read_text(encoding="utf-8")
    raw_front, body = _split_front_matter(text)
    front = _load_front_matter(raw_front, path)

    decks = tuple(
        kind
        for kind in front.get("decks", [])
        if isinstance(kind, str) and kind.strip().lower() in _VALID_DECK_KINDS
    )

    doc = LessonDoc(
        slug=_ensure_str(front, "lesson_slug", path),
        title=_ensure_str(front, "title", path),
        level_score=_ensure_int(front, "level_score", path),
        difficulty=_ensure_str(front, "difficulty", path),
        vocabulary=_parse_vocabulary(body),
        fillblanks=_parse_fillblanks(body),
        concepts=_parse_concepts(body),
        exercises=_parse_exercises(body),
    )

    return LessonParseResult(
        doc=doc,
        decks=decks,
        front_matter=front,
        source_path=path,
        raw_text=text,
        body_markdown=body,
    )


def sync_lesson(parsed: LessonParseResult, lesson_id: int | None = None) -> None:
    """Persist lesson metadata and cards into the database."""

    init_db()
    if lesson_id is None:
        lesson_id = get_or_create_lesson(
            slug=parsed.doc.slug,
            title=parsed.doc.title,
            level_score=parsed.doc.level_score,
            difficulty=parsed.doc.difficulty,
        )

    deck_ids: dict[str, int] = {}
    for deck_kind in parsed.decks or ("vocab", "fillblank"):
        normalized = deck_kind.strip().lower()
        if normalized not in _VALID_DECK_KINDS:
            continue
        label = _DECK_LABELS.get(normalized, normalized.title())
        deck_name = f"{parsed.doc.title} · {label}"
        deck_ids[normalized] = get_or_create_deck(lesson_id, normalized, deck_name)

    if "vocab" in deck_ids:
        for entry in parsed.doc.vocabulary:
            fields = _build_vocab_card(parsed.doc, lesson_id, deck_ids["vocab"], entry)
            upsert_card_by_key(fields)

    if "fillblank" in deck_ids:
        for index, entry in enumerate(parsed.doc.fillblanks, start=1):
            fields = _build_fillblank_card(parsed.doc, lesson_id, deck_ids["fillblank"], entry, index)
            upsert_card_by_key(fields)

        offset = len(parsed.doc.fillblanks)
        for index, exercise in enumerate(parsed.doc.exercises, start=1):
            fields = _build_exercise_card(
                parsed.doc,
                lesson_id,
                deck_ids["fillblank"],
                exercise,
                offset + index,
            )
            upsert_card_by_key(fields)


def import_lessons(paths: Sequence[Path]) -> None:
    for path in paths:
        try:
            parsed = load_lesson(path)
        except LessonParseError as exc:
            print(f"Skipping {path}: {exc}")
            continue
        sync_lesson(parsed)
        print(f"Imported {path}")


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Import Spanish Vibes lessons into the database")
    parser.add_argument(
        "paths",
        nargs="*",
        help="Lesson markdown files to import. Defaults to all lessons in content/lessons.",
    )
    args = parser.parse_args(argv)

    if args.paths:
        lesson_paths = [Path(p).resolve() for p in args.paths]
    else:
        root = Path.cwd()
        candidates = (root / "content" / "lessons").glob("*.md")
        lesson_paths = sorted(path.resolve() for path in candidates)

    if not lesson_paths:
        parser.error("No lesson files found to import.")

    import_lessons(lesson_paths)


def _split_front_matter(text: str) -> tuple[str, str]:
    stripped = text.lstrip()
    if not stripped:
        raise LessonParseError("Lesson is empty")
    if not stripped.startswith(FRONT_MATTER_DELIMITER):
        raise LessonParseError("Lesson is missing front matter header")

    parts = stripped.split(FRONT_MATTER_DELIMITER, 2)
    if len(parts) < 3:
        raise LessonParseError("Lesson front matter is not properly delimited")
    _, front, remainder = parts
    if remainder.startswith("\n"):
        remainder = remainder[1:]
    return front.strip(), remainder


def _load_front_matter(raw_front: str, path: Path) -> dict[str, Any]:
    try:
        loaded = yaml.safe_load(raw_front) or {}
    except yaml.YAMLError as exc:  # pragma: no cover - defensive
        raise LessonParseError(f"Invalid front matter in {path}: {exc}") from exc
    if not isinstance(loaded, dict):
        raise LessonParseError(f"Front matter must be a mapping in {path}")
    return loaded


def _ensure_str(data: dict[str, Any], key: str, path: Path) -> str:
    value = data.get(key)
    if not isinstance(value, str):
        raise LessonParseError(f"Expected string for '{key}' in {path}")
    return value.strip()


def _ensure_int(data: dict[str, Any], key: str, path: Path) -> int:
    value = data.get(key)
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    raise LessonParseError(f"Expected integer for '{key}' in {path}")


def _parse_vocabulary(body: str) -> list[LessonVocabularyEntry]:
    entries: list[LessonVocabularyEntry] = []
    for table in _iter_tables(body, filter_keyword="vocab"):
        entries.extend(_parse_vocab_table(table))
    return entries


def _iter_tables(body: str, filter_keyword: str | None = None) -> Iterator[list[str]]:
    lines = body.splitlines()
    total = len(lines)
    i = 0
    while i < total:
        line = lines[i].strip()
        if line.startswith("##") and (filter_keyword is None or filter_keyword in line.lower()):
            i += 1
            while i < total and not lines[i].strip():
                i += 1
            table_lines: list[str] = []
            while i < total:
                candidate = lines[i]
                stripped = candidate.strip()
                if not stripped:
                    break
                if "|" not in candidate:
                    break
                table_lines.append(candidate)
                i += 1
            if table_lines:
                yield table_lines
        else:
            i += 1


def _parse_vocab_table(table_lines: Iterable[str]) -> list[LessonVocabularyEntry]:
    rows = [_split_table_row(line) for line in table_lines]
    if not rows:
        return []
    header = rows[0]
    data_rows = rows[2:] if len(rows) > 2 and _is_separator_row(rows[1]) else rows[1:]
    entries: list[LessonVocabularyEntry] = []
    span_index = _column_index(header, "spanish")
    eng_index = _column_index(header, "english")

    for row in data_rows:
        if span_index is None or eng_index is None:
            break
        spanish = row[span_index].strip()
        english = row[eng_index].strip()
        if spanish and english:
            entries.append(LessonVocabularyEntry(spanish=spanish, english=english))
    return entries


def _split_table_row(line: str) -> list[str]:
    stripped = line.strip()
    if stripped.startswith("|") and stripped.endswith("|"):
        stripped = stripped[1:-1]
    parts = [part.strip() for part in stripped.split("|")]
    return parts


def _is_separator_row(row: list[str]) -> bool:
    return all(set(cell) <= {"-", ":"} for cell in row if cell)


def _column_index(header: list[str], keyword: str) -> int | None:
    lowered = [cell.lower() for cell in header]
    for index, cell in enumerate(lowered):
        if keyword in cell:
            return index
    return None


_ARROW_PATTERN = re.compile(r"→")
_BLANK_PATTERN = re.compile(r"___")
_LEADING_NUMBER = re.compile(r"^\d+\.|^[-*]")
_CODE_TICKS = re.compile(r"`+")


def _parse_fillblanks(body: str) -> list[LessonFillBlankEntry]:
    entries: list[LessonFillBlankEntry] = []
    for line in body.splitlines():
        if "→" not in line or "___" not in line:
            continue
        left, right = line.split("→", 1)
        spanish = _clean_inline(left)
        solution = _clean_inline(right)
        if not spanish or not solution:
            continue
        entries.append(
            LessonFillBlankEntry(
                spanish=spanish,
                solution=solution,
                english="",
            )
        )
    return entries


def _clean_inline(text: str) -> str:
    stripped = _LEADING_NUMBER.sub("", text).strip()
    stripped = _CODE_TICKS.sub("", stripped)
    return stripped.strip()


_CONCEPT_BLOCK = re.compile(r"```concept\n(.*?)```", re.DOTALL | re.IGNORECASE)
_EXERCISE_BLOCK = re.compile(r"```exercise\n(.*?)```", re.DOTALL | re.IGNORECASE)


def _parse_concepts(body: str) -> list[LessonConcept]:
    concepts: list[LessonConcept] = []
    for match in _CONCEPT_BLOCK.finditer(body):
        block = match.group(1)
        data = yaml.safe_load(block) or {}
        if not isinstance(data, dict):
            continue
        kind = str(data.get("kind", "")).strip()
        concept_id = str(data.get("id", "")).strip()
        if not kind or not concept_id:
            continue
        examples_raw = data.get("examples", [])
        examples: list[LessonConceptExample] = []
        if isinstance(examples_raw, list):
            for example in examples_raw:
                if isinstance(example, dict):
                    text = str(example.get("text", "")).strip()
                    english = str(example.get("english", "")).strip()
                else:
                    text = str(example).strip()
                    english = ""
                if text:
                    examples.append(LessonConceptExample(text=text, english=english))
        concepts.append(LessonConcept(kind=kind, id=concept_id, examples=examples))
    return concepts


def _parse_exercises(body: str) -> list[LessonExercise]:
    exercises: list[LessonExercise] = []
    for match in _EXERCISE_BLOCK.finditer(body):
        block = match.group(1)
        data = yaml.safe_load(block) or {}
        if not isinstance(data, dict):
            continue
        prompt = str(data.get("prompt", "")).strip()
        if not prompt:
            continue
        normalized: LessonExercise = {"prompt": prompt}
        for key in ("type", "answer"):
            if key in data and isinstance(data[key], str):
                normalized[key] = data[key]
        if "options" in data and isinstance(data["options"], list):
            normalized["options"] = [str(option) for option in data["options"]]
        if "expected_keys" in data and isinstance(data["expected_keys"], list):
            normalized["expected_keys"] = [str(value) for value in data["expected_keys"]]
        feedback = data.get("feedback")
        if isinstance(feedback, dict):
            fb: LessonExerciseFeedback = {}
            if "correct" in feedback and isinstance(feedback["correct"], str):
                fb["correct"] = feedback["correct"]
            if "incorrect" in feedback and isinstance(feedback["incorrect"], str):
                fb["incorrect"] = feedback["incorrect"]
            if fb:
                normalized["feedback"] = fb
        exercises.append(normalized)
    return exercises


def _build_vocab_card(
    doc: LessonDoc,
    lesson_id: int,
    deck_id: int,
    entry: LessonVocabularyEntry,
) -> CardRecord:
    now = now_iso()
    content_key = _content_key(doc.slug, "vocab", f"{entry['spanish']}|{entry['english']}")
    extra = {
        "english": entry.get("english"),
        "spanish": entry.get("spanish"),
        "source": "lesson",
    }
    return CardRecord(
        deck_id=deck_id,
        lesson_id=lesson_id,
        kind="vocab",
        prompt=entry["english"],
        solution=entry["spanish"],
        direction="en_to_es",
        extra_json=json.dumps(extra, ensure_ascii=False),
        content_key=content_key,
        due_at=now,
        created_at=now,
        updated_at=now,
    )


def _build_fillblank_card(
    doc: LessonDoc,
    lesson_id: int,
    deck_id: int,
    entry: LessonFillBlankEntry,
    index: int,
) -> CardRecord:
    now = now_iso()
    payload = {
        "spanish": entry.get("spanish"),
        "solution": entry.get("solution"),
        "english": entry.get("english", ""),
        "source": "lesson",
        "sequence": index,
    }
    content_key = _content_key(doc.slug, "fillblank", f"{index}:{entry['spanish']}")
    return CardRecord(
        deck_id=deck_id,
        lesson_id=lesson_id,
        kind="fillblank",
        prompt=entry["spanish"],
        solution=entry["solution"],
        direction=None,
        extra_json=json.dumps(payload, ensure_ascii=False),
        content_key=content_key,
        due_at=now,
        created_at=now,
        updated_at=now,
    )


def _build_exercise_card(
    doc: LessonDoc,
    lesson_id: int,
    deck_id: int,
    exercise: LessonExercise,
    index: int,
) -> CardRecord:
    now = now_iso()
    answer: str = exercise.get("answer", "")
    if not answer:
        expected = exercise.get("expected_keys")
        if expected:
            answer = " / ".join(expected)
    payload = {
        "exercise": exercise,
        "source": "lesson",
        "sequence": index,
    }
    content_key = _content_key(doc.slug, "exercise", f"{index}:{exercise['prompt']}")
    return CardRecord(
        deck_id=deck_id,
        lesson_id=lesson_id,
        kind="fillblank",
        prompt=exercise["prompt"],
        solution=answer,
        direction=None,
        extra_json=json.dumps(payload, ensure_ascii=False),
        content_key=content_key,
        due_at=now,
        created_at=now,
        updated_at=now,
    )


def _content_key(slug: str, kind: str, payload: str) -> str:
    digest = sha1(payload.encode("utf-8")).hexdigest()[:12]
    safe_slug = _slugify(slug)
    return f"{safe_slug}:{kind}:{digest}"


_SLUG_CLEAN = re.compile(r"[^a-z0-9]+")


def _slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_text = "".join(ch for ch in normalized if not unicodedata.combining(ch)).lower()
    cleaned = _SLUG_CLEAN.sub("-", ascii_text).strip("-")
    return cleaned or "lesson"


if __name__ == "__main__":  # pragma: no cover - manual execution
    main()
