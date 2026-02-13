"""AI MCQ generation for Flow Mode v2 + offline fallback from existing cards."""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any

from .concepts import load_concepts
from .flow_db import count_cached_mcqs, get_all_concept_knowledge, save_mcq_batch


def ai_available() -> bool:
    """Return True if an OpenAI API key is configured."""
    return bool(os.environ.get("OPENAI_API_KEY"))


def _get_client() -> Any:
    """Lazy-load the OpenAI client."""
    try:
        from openai import OpenAI
        return OpenAI()
    except Exception:
        return None


MIN_CACHE_COUNT = 5


def ensure_cache_populated(concept_id: str) -> int:
    """Check cache count for concept, generate if < MIN_CACHE_COUNT. Returns count."""
    count = count_cached_mcqs(concept_id)
    if count >= MIN_CACHE_COUNT:
        return count

    if ai_available():
        generated = generate_mcq_batch(concept_id)
        return count + len(generated)

    # Offline fallback
    converted = convert_existing_cards_to_mcq(concept_id)
    return count + len(converted)


def generate_mcq_batch(concept_id: str, count: int = 15) -> list[int]:
    """Generate MCQ batch via GPT-4o-mini. Returns list of saved MCQ IDs."""
    if not ai_available():
        return []

    client = _get_client()
    if client is None:
        return []

    concepts = load_concepts()
    concept = concepts.get(concept_id)
    if concept is None:
        return []

    # Build concept list for misconception mapping
    all_concept_ids = [c.id for c in concepts.values() if c.difficulty_level <= concept.difficulty_level + 1]

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a Spanish language education expert creating A1-level MCQ questions. "
                        "Generate multiple-choice questions with EXACTLY 1 unambiguous correct answer and 3 wrong distractors. "
                        "Each distractor should map to a specific misconception concept from the provided list. "
                        "CRITICAL RULES:\n"
                        "- Every question MUST have exactly ONE correct answer. Never create questions where multiple options could be valid.\n"
                        "- NEVER use open-ended fill-in-the-blank like 'Quiero _____' where any noun fits.\n"
                        "- Good question types: translation ('What does X mean?'), grammar ('Which is correct?'), "
                        "vocabulary matching ('How do you say X in Spanish?').\n"
                        "- Distractors should be plausible but clearly wrong (e.g. wrong gender, wrong conjugation, wrong meaning).\n"
                        "Return ONLY a JSON array, no extra text."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Generate {count} A1 Spanish MCQ questions for the concept '{concept.name}' "
                        f"(id: {concept_id}).\n\n"
                        f"Concept teach content:\n{concept.teach_content}\n\n"
                        f"Available misconception concept IDs: {all_concept_ids}\n\n"
                        f"Return a JSON array where each item has:\n"
                        f'- "question": the question text\n'
                        f'- "correct_answer": the correct answer\n'
                        f'- "distractors": array of 3 objects with "text" and "misconception" (concept_id)\n'
                        f'- "difficulty": 1-3 (1=easy, 2=medium, 3=hard)\n\n'
                        f"Use these question types: translation (English↔Spanish), 'which is correct' grammar, "
                        f"vocabulary matching. Do NOT use open-ended fill-in-the-blank where multiple answers work."
                    ),
                },
            ],
            temperature=0.8,
            max_tokens=4000,
        )

        content = response.choices[0].message.content or ""
        content = content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[-1]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()

        items = json.loads(content)
        if not isinstance(items, list):
            return []

        cards: list[dict[str, Any]] = []
        for item in items:
            question = item.get("question", "")
            correct = item.get("correct_answer", "")
            distractors = item.get("distractors", [])
            difficulty = item.get("difficulty", 1)

            if not question or not correct:
                continue

            content_hash = _mcq_hash(concept_id, question, correct)
            cards.append({
                "question": question,
                "correct_answer": correct,
                "distractors": distractors,
                "difficulty": difficulty,
                "source": "ai",
                "content_hash": content_hash,
            })

        if cards:
            return save_mcq_batch(concept_id, cards)
        return []

    except Exception:
        return []


def convert_existing_cards_to_mcq(concept_id: str) -> list[int]:
    """Convert existing DB cards to MCQ format without API key.

    Pull vocab/verb cards and generate distractors from same-lesson solutions.
    """
    from .db import _open_connection

    concepts = load_concepts()
    concept = concepts.get(concept_id)
    if concept is None:
        return []

    # Get all vocab cards to build a distractor pool
    with _open_connection() as conn:
        rows = conn.execute(
            "SELECT prompt, solution, kind FROM cards WHERE kind IN ('vocab', 'verbs') ORDER BY RANDOM() LIMIT 200"
        ).fetchall()

    if not rows:
        return []

    # Build solution pool for distractors
    solution_pool: list[str] = []
    prompt_pool: list[str] = []
    for row in rows:
        solution_pool.append(str(row["solution"]))
        prompt_pool.append(str(row["prompt"]))

    cards: list[dict[str, Any]] = []

    # Generate MCQs from vocab cards
    for row in rows:
        prompt = str(row["prompt"])
        solution = str(row["solution"])

        # "What does 'X' mean?" style
        distractors = _pick_distractors(solution, solution_pool, 3)
        if len(distractors) < 3:
            continue

        content_hash = _mcq_hash(concept_id, f"convert:{prompt}", solution)
        cards.append({
            "question": f"What does '{prompt}' mean?",
            "correct_answer": solution,
            "distractors": [{"text": d, "misconception": concept_id} for d in distractors],
            "difficulty": 1,
            "source": "converted",
            "content_hash": content_hash,
        })

        if len(cards) >= 20:
            break

    if cards:
        return save_mcq_batch(concept_id, cards)
    return []


def prefetch_next_concepts(knowledge: dict | None = None) -> None:
    """Background: populate MCQ cache for learning + next-new concepts."""
    if knowledge is None:
        knowledge = get_all_concept_knowledge()

    from .concepts import get_next_new_concepts
    from .bkt import is_mastered

    # Learning concepts
    for concept_id, ck in knowledge.items():
        if ck.n_attempts > 0 and not is_mastered(ck.p_mastery, ck.n_attempts):
            ensure_cache_populated(concept_id)

    # Next new concepts
    for concept_id in get_next_new_concepts(knowledge, limit=3):
        ensure_cache_populated(concept_id)


def _pick_distractors(correct: str, pool: list[str], count: int) -> list[str]:
    """Pick `count` unique distractors from pool that differ from correct."""
    import random
    candidates = [s for s in set(pool) if s.lower() != correct.lower()]
    random.shuffle(candidates)
    return candidates[:count]


def _mcq_hash(concept_id: str, question: str, answer: str) -> str:
    raw = f"mcq:{concept_id}:{question}:{answer}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


__all__ = [
    "ai_available",
    "convert_existing_cards_to_mcq",
    "ensure_cache_populated",
    "generate_mcq_batch",
    "prefetch_next_concepts",
]
