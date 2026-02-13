from __future__ import annotations

import importlib
import sqlite3
from pathlib import Path

import pytest

SAMPLE_LESSON = """---
chapter_slug: ch01
lesson_slug: ch01-99-sample
title: Sample Lesson Title
order_index: 99
summary: "Test lesson for automation"
tags: [test, sample]
decks: [vocab, fillblank]
status: draft
level_score: 3
difficulty: Beginner
---

# Lesson Text

Introduction paragraph.

## Vocabulary

spanish | english | note
---|---|---
hola | hello | greeting
adiós | goodbye | farewell

## Practice

1. `Yo ___ (saludar) a mis amigos.` → `saludo`
2. `No ___ (decir) adiós en voz baja.` → `dices`

```concept
id: noun-agreement
kind: agreement_rule
examples:
  - text: "La casa blanca"
    english: "The white house"
  - text: "Los libros interesantes"
    english: "The interesting books"
```

```exercise
type: mcq
prompt: "Choose the correct greeting."
options:
  - "Hola"
  - "Adiós"
answer: "Hola"
feedback:
  correct: "Nice work."
  incorrect: "We start with 'Hola'."
```
"""


@pytest.fixture()
def lessons_env(tmp_path, monkeypatch):
    lesson_path = tmp_path / "sample.md"
    lesson_path.write_text(SAMPLE_LESSON, encoding="utf-8")

    db_path = tmp_path / "lessons.db"
    monkeypatch.setenv("SPANISH_VIBES_DB_PATH", str(db_path))

    db_module = importlib.import_module("spanish_vibes.db")
    importlib.reload(db_module)
    db_module.init_db()

    lessons_module = importlib.import_module("spanish_vibes.lessons")
    importlib.reload(lessons_module)

    return lesson_path, db_path, lessons_module, db_module


def test_load_lesson_parses_components(lessons_env):
    lesson_path, _, lessons_module, _ = lessons_env

    parsed = lessons_module.load_lesson(lesson_path)

    assert parsed.doc.slug == "ch01-99-sample"
    assert parsed.decks == ("vocab", "fillblank")
    assert len(parsed.doc.vocabulary) == 2
    assert {entry["spanish"] for entry in parsed.doc.vocabulary} == {"hola", "adiós"}
    assert len(parsed.doc.fillblanks) == 2
    assert parsed.doc.fillblanks[0]["solution"] == "saludo"
    assert len(parsed.doc.concepts) == 1
    assert parsed.doc.concepts[0]["id"] == "noun-agreement"
    assert len(parsed.doc.exercises) == 1


def test_sync_lesson_creates_cards(lessons_env):
    lesson_path, db_path, lessons_module, _ = lessons_env

    parsed = lessons_module.load_lesson(lesson_path)
    lessons_module.sync_lesson(parsed)

    connection = sqlite3.connect(db_path)
    try:
        connection.row_factory = sqlite3.Row
        lessons = connection.execute("SELECT slug, title FROM lessons").fetchall()
        assert {(row["slug"], row["title"]) for row in lessons} == {
            ("ch01-99-sample", "Sample Lesson Title")
        }
        cards = connection.execute(
            "SELECT kind, prompt, solution, direction FROM cards ORDER BY kind, prompt"
        ).fetchall()
        assert len(cards) == 5
        vocab_cards = [row for row in cards if row["kind"] == "vocab"]
        fill_cards = [row for row in cards if row["kind"] == "fillblank"]
        assert len(vocab_cards) == 2
        assert {row["prompt"] for row in vocab_cards} == {"hello", "goodbye"}
        assert len(fill_cards) == 3
        prompts = {row["prompt"] for row in fill_cards}
        assert any("saludar" in prompt for prompt in prompts)
        assert any("Choose the correct greeting" in prompt for prompt in prompts)
    finally:
        connection.close()


def test_import_lessons_skips_invalid_files(lessons_env, capsys):
    lesson_path, db_path, lessons_module, _ = lessons_env
    empty_path = lesson_path.parent / "empty.md"
    empty_path.write_text("", encoding="utf-8")

    lessons_module.import_lessons([empty_path, lesson_path])

    out = capsys.readouterr().out
    assert "Skipping" in out and str(empty_path) in out
    assert "Imported" in out and str(lesson_path) in out

    connection = sqlite3.connect(db_path)
    try:
        connection.row_factory = sqlite3.Row
        lessons = connection.execute("SELECT slug FROM lessons").fetchall()
        assert {row["slug"] for row in lessons} == {"ch01-99-sample"}
    finally:
        connection.close()
