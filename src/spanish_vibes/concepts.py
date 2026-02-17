"""Concept graph: YAML loader, DAG validation, prerequisite checking."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .db import _open_connection, get_current_user_id, now_iso
from .models import Concept, ConceptKnowledge

PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_ROOT.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
CONCEPTS_FILE = DATA_DIR / "concepts.yaml"

_concept_cache: dict[str, Concept] | None = None


def load_concepts(path: Path | None = None) -> dict[str, Concept]:
    """Parse YAML file and return dict[concept_id, Concept]. Cached in memory."""
    global _concept_cache
    if _concept_cache is not None and path is None:
        return _concept_cache

    file_path = path or CONCEPTS_FILE
    with open(file_path) as f:
        raw: list[dict[str, Any]] = yaml.safe_load(f)

    concepts: dict[str, Concept] = {}
    for entry in raw:
        concept = Concept(
            id=entry["id"],
            name=entry["name"],
            description=entry.get("description", ""),
            difficulty_level=entry.get("difficulty_level", 1),
            teach_content=entry.get("teach_content", ""),
            prerequisites=entry.get("prerequisites", []),
        )
        concepts[concept.id] = concept

    if path is None:
        _concept_cache = concepts
    return concepts


def clear_cache() -> None:
    """Clear the in-memory concept cache."""
    global _concept_cache
    _concept_cache = None


def validate_dag(concepts: dict[str, Concept]) -> list[str]:
    """Topological sort the concept DAG. Returns ordered list of concept IDs.
    Raises ValueError if there are cycles or missing prerequisites.
    """
    # Check all prerequisites exist
    for concept in concepts.values():
        for prereq in concept.prerequisites:
            if prereq not in concepts:
                raise ValueError(
                    f"Concept '{concept.id}' has unknown prerequisite '{prereq}'"
                )

    # Kahn's algorithm for topological sort
    in_degree: dict[str, int] = {cid: 0 for cid in concepts}
    for concept in concepts.values():
        for prereq in concept.prerequisites:
            in_degree[concept.id] += 1

    # Adjacency: prereq -> list of concepts that depend on it
    adj: dict[str, list[str]] = {cid: [] for cid in concepts}
    for concept in concepts.values():
        for prereq in concept.prerequisites:
            adj[prereq].append(concept.id)

    queue: list[str] = [cid for cid, deg in in_degree.items() if deg == 0]
    queue.sort(key=lambda cid: (concepts[cid].difficulty_level, cid))
    result: list[str] = []

    while queue:
        node = queue.pop(0)
        result.append(node)
        for neighbor in sorted(adj[node]):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)
        queue.sort(key=lambda cid: (concepts[cid].difficulty_level, cid))

    if len(result) != len(concepts):
        raise ValueError("Cycle detected in concept prerequisite graph")

    return result


def topological_order(concepts: dict[str, Concept] | None = None) -> list[str]:
    """Return full teaching sequence (topological order)."""
    if concepts is None:
        concepts = load_concepts()
    return validate_dag(concepts)


def prerequisites_met(
    concept_id: str,
    knowledge: dict[str, ConceptKnowledge],
    concepts: dict[str, Concept] | None = None,
) -> bool:
    """True if all prereqs have p_mastery >= 0.90 AND n_attempts >= 5."""
    if concepts is None:
        concepts = load_concepts()
    concept = concepts.get(concept_id)
    if concept is None:
        return False
    if not concept.prerequisites:
        return True

    from .bkt import MASTERY_THRESHOLD, MIN_ATTEMPTS_FOR_MASTERY

    for prereq_id in concept.prerequisites:
        ck = knowledge.get(prereq_id)
        if ck is None:
            return False
        if ck.p_mastery < MASTERY_THRESHOLD or ck.n_attempts < MIN_ATTEMPTS_FOR_MASTERY:
            return False
    return True


def get_next_new_concepts(
    knowledge: dict[str, ConceptKnowledge],
    concepts: dict[str, Concept] | None = None,
    limit: int = 3,
) -> list[str]:
    """Unseen concepts whose prerequisites are met, ordered by tier."""
    if concepts is None:
        concepts = load_concepts()

    candidates: list[str] = []
    for concept_id in topological_order(concepts):
        ck = knowledge.get(concept_id)
        if ck is not None and ck.n_attempts > 0:
            continue  # Already started
        if prerequisites_met(concept_id, knowledge, concepts):
            candidates.append(concept_id)
            if len(candidates) >= limit:
                break
    return candidates


def seed_concepts_to_db(path: Path | None = None) -> int:
    """INSERT OR REPLACE concepts + prerequisites, init concept_knowledge rows.
    Returns number of concepts seeded.
    """
    concepts = load_concepts(path)
    validate_dag(concepts)
    timestamp = now_iso()
    user_id = get_current_user_id() or 1

    with _open_connection() as conn:
        for concept in concepts.values():
            conn.execute(
                """
                INSERT OR REPLACE INTO concepts (id, name, description, difficulty_level, teach_content, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    concept.id,
                    concept.name,
                    concept.description,
                    concept.difficulty_level,
                    concept.teach_content,
                    timestamp,
                ),
            )

        # Clear and re-insert prerequisites
        conn.execute("DELETE FROM concept_prerequisites")
        for concept in concepts.values():
            for prereq_id in concept.prerequisites:
                conn.execute(
                    "INSERT INTO concept_prerequisites (concept_id, prerequisite_id) VALUES (?, ?)",
                    (concept.id, prereq_id),
                )

        # Init knowledge rows (don't overwrite existing)
        for concept_id in concepts:
            existing = conn.execute(
                "SELECT concept_id FROM concept_knowledge WHERE user_id = ? AND concept_id = ?",
                (user_id, concept_id),
            ).fetchone()
            if existing is None:
                conn.execute(
                    """
                    INSERT INTO concept_knowledge (user_id, concept_id, p_mastery, n_attempts, n_correct, n_wrong, teach_shown, updated_at)
                    VALUES (?, ?, 0.0, 0, 0, 0, 0, ?)
                    """,
                    (user_id, concept_id, timestamp),
                )
        conn.commit()

    return len(concepts)


__all__ = [
    "clear_cache",
    "get_next_new_concepts",
    "load_concepts",
    "prerequisites_met",
    "seed_concepts_to_db",
    "topological_order",
    "validate_dag",
]
