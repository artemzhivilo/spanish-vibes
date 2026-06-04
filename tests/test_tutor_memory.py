from __future__ import annotations

from spanish_vibes.models import Concept, ConceptKnowledge
from spanish_vibes import tutor_memory


def _concept(
    concept_id: str,
    tier: int,
    prerequisites: list[str] | None = None,
) -> Concept:
    return Concept(
        id=concept_id,
        name=concept_id,
        description="",
        difficulty_level=tier,
        teach_content="",
        prerequisites=prerequisites or [],
    )


def _knowledge(
    concept_id: str,
    p_mastery: float,
    n_attempts: int,
) -> ConceptKnowledge:
    return ConceptKnowledge(
        concept_id=concept_id,
        p_mastery=p_mastery,
        n_attempts=n_attempts,
        n_correct=0,
        n_wrong=0,
        teach_shown=False,
        last_seen_at=None,
        updated_at="",
    )


def test_build_curriculum_context_handles_no_rows(monkeypatch) -> None:
    monkeypatch.setattr(tutor_memory, "get_all_concept_knowledge", lambda: {})
    monkeypatch.setattr(tutor_memory, "load_concepts", lambda: {})

    text = tutor_memory.build_curriculum_context("u1")

    assert "New learner - no curriculum data yet." in text


def test_build_curriculum_context_handles_all_zero_rows(monkeypatch) -> None:
    concepts = {
        "greetings": _concept("greetings", 1),
        "articles_definite": _concept("articles_definite", 1),
    }
    knowledge = {
        "greetings": _knowledge("greetings", 0.0, 0),
        "articles_definite": _knowledge("articles_definite", 0.0, 0),
    }
    monkeypatch.setattr(tutor_memory, "load_concepts", lambda: concepts)
    monkeypatch.setattr(tutor_memory, "get_all_concept_knowledge", lambda: knowledge)

    text = tutor_memory.build_curriculum_context("u1")

    assert "New learner - no curriculum data yet." in text


def test_build_curriculum_context_reports_progress_next_and_stuck(monkeypatch) -> None:
    concepts = {
        "greetings": _concept("greetings", 1),
        "numbers_1_20": _concept("numbers_1_20", 1),
        "articles_definite": _concept("articles_definite", 2, ["greetings"]),
        "present_tense_regular": _concept("present_tense_regular", 2, ["greetings"]),
        "adjective_agreement": _concept("adjective_agreement", 2, ["greetings"]),
    }
    knowledge = {
        "greetings": _knowledge("greetings", 0.95, 7),
        "numbers_1_20": _knowledge("numbers_1_20", 0.92, 5),
        "articles_definite": _knowledge("articles_definite", 0.65, 8),
        "present_tense_regular": _knowledge("present_tense_regular", 0.72, 12),
        "adjective_agreement": _knowledge("adjective_agreement", 0.0, 0),
    }
    monkeypatch.setattr(tutor_memory, "load_concepts", lambda: concepts)
    monkeypatch.setattr(tutor_memory, "get_all_concept_knowledge", lambda: knowledge)

    text = tutor_memory.build_curriculum_context("u1")

    assert "Current tier: 2 (Basic Grammar)" in text
    assert "Tier 1 (Foundations): 2/2 mastered" in text
    assert "Tier 2 (Basic Grammar): 0/3 mastered, 2 in progress" in text
    assert "🔄 articles_definite - 0.65 mastery (8 attempts)" in text
    assert "🔄 present_tense_regular - 0.72 mastery (12 attempts)" in text
    assert "Next available: adjective_agreement" in text
    assert (
        "Avoidance alert: articles_definite has 8 attempts but only 0.65 mastery"
        in text
    )


def test_build_planner_context_includes_curriculum_section(monkeypatch) -> None:
    monkeypatch.setattr(tutor_memory, "read_learner_profile", lambda _u: "PROFILE")
    monkeypatch.setattr(
        tutor_memory, "read_session_journal", lambda _u, last_n=5: "JOURNAL"
    )
    monkeypatch.setattr(tutor_memory, "read_grammar_notes", lambda _u: "GRAMMAR")
    monkeypatch.setattr(
        tutor_memory,
        "build_curriculum_context",
        lambda _u: "Current tier: 1 (Foundations) - 0% complete",
    )

    text = tutor_memory.build_planner_context("u1")

    assert "## CURRICULUM STATUS" in text
    assert "Current tier: 1 (Foundations) - 0% complete" in text
