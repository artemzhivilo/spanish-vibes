from __future__ import annotations

import importlib
from pathlib import Path

import pytest


@pytest.fixture()
def lesson_file(tmp_path: Path) -> Path:
    md = tmp_path / "lesson.md"
    md.write_text(
        """---
chapter_slug: ch99
lesson_slug: ch99-01-test
title: Cache Test Lesson
order_index: 999
summary: "Testing cache"
tags: [test]
decks: [vocab]
status: draft
level_score: 5
difficulty: Sample
---

# Heading

Hello **world**.""",
        encoding="utf-8",
    )
    return md


def test_importer_stores_html(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, lesson_file: Path) -> None:
    db_path = tmp_path / "cache.db"
    monkeypatch.setenv("SPANISH_VIBES_DB_PATH", str(db_path))

    import spanish_vibes.db as db_module
    importlib.reload(db_module)
    db_module.init_db()

    import spanish_vibes.importer as importer
    importlib.reload(importer)
    importer.main(["--glob", str(lesson_file), "--store-html"])

    row = db_module.get_lesson_by_slug("ch99-01-test")
    assert row is not None
    first_sha = row["content_sha"]
    assert first_sha
    assert "<strong>world</strong>" in row["content_html"]

    lesson_file.write_text(
        lesson_file.read_text(encoding="utf-8").replace("Hello", "Hola"),
        encoding="utf-8",
    )

    importer.main(["--glob", str(lesson_file), "--store-html"])
    row_after = db_module.get_lesson_by_slug("ch99-01-test")
    assert row_after is not None
    assert row_after["content_sha"] != first_sha
    assert "Hola" in row_after["content_html"]
