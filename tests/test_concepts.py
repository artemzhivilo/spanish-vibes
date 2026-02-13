"""Tests for concepts.py: YAML loading, DAG validation, prerequisites."""

from __future__ import annotations

import pytest

from spanish_vibes.models import Concept, ConceptKnowledge


@pytest.fixture(autouse=True)
def fresh_db(tmp_path):
    from spanish_vibes import db
    db.DB_PATH = tmp_path / "test.db"
    db.init_db()
    from spanish_vibes.concepts import clear_cache
    clear_cache()
    yield


@pytest.fixture
def sample_concepts() -> dict[str, Concept]:
    return {
        "greetings": Concept(
            id="greetings", name="Greetings", description="",
            difficulty_level=1, teach_content="Hola", prerequisites=[],
        ),
        "pronouns": Concept(
            id="pronouns", name="Pronouns", description="",
            difficulty_level=2, teach_content="Yo, tú",
            prerequisites=["greetings"],
        ),
        "ser": Concept(
            id="ser", name="Ser", description="",
            difficulty_level=3, teach_content="soy, eres",
            prerequisites=["pronouns"],
        ),
    }


class TestValidateDAG:
    def test_valid_dag(self, sample_concepts):
        from spanish_vibes.concepts import validate_dag
        order = validate_dag(sample_concepts)
        assert order == ["greetings", "pronouns", "ser"]

    def test_cycle_detection(self):
        from spanish_vibes.concepts import validate_dag
        concepts = {
            "a": Concept(id="a", name="A", description="", difficulty_level=1,
                         teach_content="", prerequisites=["b"]),
            "b": Concept(id="b", name="B", description="", difficulty_level=1,
                         teach_content="", prerequisites=["a"]),
        }
        with pytest.raises(ValueError, match="Cycle"):
            validate_dag(concepts)

    def test_missing_prerequisite(self):
        from spanish_vibes.concepts import validate_dag
        concepts = {
            "a": Concept(id="a", name="A", description="", difficulty_level=1,
                         teach_content="", prerequisites=["nonexistent"]),
        }
        with pytest.raises(ValueError, match="unknown prerequisite"):
            validate_dag(concepts)


class TestPrerequisitesMet:
    def test_no_prereqs_always_met(self, sample_concepts):
        from spanish_vibes.concepts import prerequisites_met
        assert prerequisites_met("greetings", {}, sample_concepts) is True

    def test_unmet_prereqs(self, sample_concepts):
        from spanish_vibes.concepts import prerequisites_met
        knowledge = {
            "greetings": ConceptKnowledge(
                concept_id="greetings", p_mastery=0.5, n_attempts=3,
                n_correct=2, n_wrong=1, teach_shown=True,
                last_seen_at=None,
            ),
        }
        assert prerequisites_met("pronouns", knowledge, sample_concepts) is False

    def test_met_prereqs(self, sample_concepts):
        from spanish_vibes.concepts import prerequisites_met
        knowledge = {
            "greetings": ConceptKnowledge(
                concept_id="greetings", p_mastery=0.95, n_attempts=10,
                n_correct=9, n_wrong=1, teach_shown=True,
                last_seen_at=None,
            ),
        }
        assert prerequisites_met("pronouns", knowledge, sample_concepts) is True

    def test_missing_knowledge_entry(self, sample_concepts):
        from spanish_vibes.concepts import prerequisites_met
        assert prerequisites_met("pronouns", {}, sample_concepts) is False


class TestGetNextNewConcepts:
    def test_returns_tier1_first(self, sample_concepts):
        from spanish_vibes.concepts import get_next_new_concepts
        result = get_next_new_concepts({}, sample_concepts)
        assert result == ["greetings"]

    def test_returns_next_after_mastery(self, sample_concepts):
        from spanish_vibes.concepts import get_next_new_concepts
        knowledge = {
            "greetings": ConceptKnowledge(
                concept_id="greetings", p_mastery=0.95, n_attempts=10,
                n_correct=9, n_wrong=1, teach_shown=True,
                last_seen_at=None,
            ),
        }
        result = get_next_new_concepts(knowledge, sample_concepts)
        assert "pronouns" in result

    def test_skips_started_concepts(self, sample_concepts):
        from spanish_vibes.concepts import get_next_new_concepts
        knowledge = {
            "greetings": ConceptKnowledge(
                concept_id="greetings", p_mastery=0.5, n_attempts=3,
                n_correct=2, n_wrong=1, teach_shown=True,
                last_seen_at=None,
            ),
        }
        result = get_next_new_concepts(knowledge, sample_concepts)
        assert "greetings" not in result


class TestLoadConceptsYAML:
    def test_load_real_yaml(self):
        from spanish_vibes.concepts import load_concepts, CONCEPTS_FILE
        if not CONCEPTS_FILE.exists():
            pytest.skip("concepts.yaml not found")
        concepts = load_concepts()
        assert len(concepts) >= 25  # We have ~35 concepts
        # All concepts have required fields
        for c in concepts.values():
            assert c.id
            assert c.name
            assert c.difficulty_level >= 1

    def test_validate_real_dag(self):
        from spanish_vibes.concepts import load_concepts, validate_dag, CONCEPTS_FILE
        if not CONCEPTS_FILE.exists():
            pytest.skip("concepts.yaml not found")
        concepts = load_concepts()
        order = validate_dag(concepts)
        assert len(order) == len(concepts)


class TestSeedConceptsToDB:
    def test_seed_and_query(self):
        from spanish_vibes.concepts import seed_concepts_to_db, CONCEPTS_FILE
        if not CONCEPTS_FILE.exists():
            pytest.skip("concepts.yaml not found")
        count = seed_concepts_to_db()
        assert count >= 25

        from spanish_vibes.db import _open_connection
        with _open_connection() as conn:
            rows = conn.execute("SELECT COUNT(*) FROM concepts").fetchone()
            assert rows[0] == count

            rows = conn.execute("SELECT COUNT(*) FROM concept_knowledge").fetchone()
            assert rows[0] == count

    def test_seed_idempotent(self):
        from spanish_vibes.concepts import seed_concepts_to_db, CONCEPTS_FILE
        if not CONCEPTS_FILE.exists():
            pytest.skip("concepts.yaml not found")
        count1 = seed_concepts_to_db()
        count2 = seed_concepts_to_db()
        assert count1 == count2
