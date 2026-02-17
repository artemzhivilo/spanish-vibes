"""AI MCQ generation for Flow Mode v2 + offline fallback from existing cards."""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any

from .concepts import load_concepts
from .flow_db import count_cached_mcqs, get_all_concept_knowledge, save_mcq_batch
from . import prompts as prompt_config


def ai_available() -> bool:
    """Return True if an OpenAI API key is configured."""
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return False
    return bool(os.environ.get("OPENAI_API_KEY"))


def _get_client() -> Any:
    """Lazy-load the OpenAI client."""
    try:
        from openai import OpenAI
        return OpenAI()
    except Exception:
        return None


MIN_CACHE_COUNT = 5


def ensure_cache_populated(concept_id: str, topic: str | None = None) -> int:
    """Check cache count for concept, generate if < MIN_CACHE_COUNT. Returns count."""
    if ai_available():
        count = count_cached_mcqs(concept_id, source="ai")
        if count >= MIN_CACHE_COUNT:
            return count
        generated = generate_mcq_batch(concept_id, topic=topic)
        if not generated and topic is not None:
            # Fallback: retry without topic
            generated = generate_mcq_batch(concept_id)
        return count + len(generated)

    # Offline fallback
    count = count_cached_mcqs(concept_id, source="converted")
    if count >= MIN_CACHE_COUNT:
        return count
    converted = convert_existing_cards_to_mcq(concept_id)
    return count + len(converted)


def generate_mcq_batch(concept_id: str, count: int = 15, topic: str | None = None) -> list[int]:
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

    # Build topic theming instruction
    topic_instruction = ""
    if topic:
        topic_instruction = (
            f"\nIMPORTANT: Theme the content around '{topic}'. "
            f"Use vocabulary and scenarios related to {topic}. "
            f"Ensure the grammar being tested is '{concept.name}', not vocabulary.\n"
        )

    try:
        mcq_sys = prompt_config.get("mcq_system", "")
        if mcq_sys:
            mcq_system_content = mcq_sys.format(topic_instruction=topic_instruction)
        else:
            mcq_system_content = (
                "You are a Spanish language education expert creating A1-level MCQ questions. "
                f"{topic_instruction}"
                "Return ONLY a JSON array, no extra text."
            )

        response = client.chat.completions.create(
            model=prompt_config.get_model("mcq"),
            messages=[
                {
                    "role": "system",
                    "content": mcq_system_content,
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
                        f"Use these question types: translation (English→Spanish or Spanish→English), "
                        f"targeted grammar ('Which correctly uses [specific concept]?'), error spotting.\n"
                        f"IMPORTANT: Every question must constrain answers to ONE correct option. "
                        f"If testing grammar, specify WHAT to test in the question itself. "
                        f"All 4 options should attempt the SAME sentence/meaning but with different grammar choices. "
                        f"Do NOT mix unrelated correct sentences as options."
                    ),
                },
            ],
            temperature=prompt_config.get_temperature("mcq"),
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

            # Validate MCQ quality — reject ambiguous or poorly constructed questions
            if not _validate_mcq(item):
                continue

            content_hash = _mcq_hash(concept_id, question, correct, topic)
            card_dict: dict[str, Any] = {
                "question": question,
                "correct_answer": correct,
                "distractors": distractors,
                "difficulty": difficulty,
                "source": "ai",
                "content_hash": content_hash,
            }
            if topic:
                card_dict["topic"] = topic
            cards.append(card_dict)

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


def _validate_mcq(item: dict[str, Any]) -> bool:
    """Reject MCQs that are likely ambiguous or poorly constructed.

    Returns True if the MCQ passes validation, False if it should be discarded.
    """
    question = item.get("question", "").strip().lower()
    correct = item.get("correct_answer", "").strip()
    distractors = item.get("distractors", [])

    if not question or not correct or len(distractors) < 3:
        return False

    # Reject vague "which is correct?" with no constraining context
    vague_patterns = ["which is correct?", "which one is correct?", "which is right?"]
    if question in vague_patterns or question.rstrip("?") in [p.rstrip("?") for p in vague_patterns]:
        return False

    # Reject if distractors are completely unrelated sentences
    # (i.e., they don't share any significant words with the correct answer)
    correct_words = set(correct.lower().split()) - {"el", "la", "los", "las", "un", "una", "es", "está", "de", "en", "a", "y", "o"}
    if correct_words:
        distractor_texts = [d.get("text", "") if isinstance(d, dict) else str(d) for d in distractors]
        shared_count = 0
        for dt in distractor_texts:
            dt_words = set(dt.lower().split())
            if correct_words & dt_words:
                shared_count += 1
        # At least 2 of 3 distractors should share vocabulary with the correct answer
        # (meaning they're variations of the same sentence, not random unrelated sentences)
        if shared_count < 2:
            return False

    return True


def _pick_distractors(correct: str, pool: list[str], count: int) -> list[str]:
    """Pick `count` unique distractors from pool that differ from correct."""
    import random
    candidates = [s for s in set(pool) if s.lower() != correct.lower()]
    random.shuffle(candidates)
    return candidates[:count]


def _mcq_hash(concept_id: str, question: str, answer: str, topic: str | None = None) -> str:
    topic_part = f":{topic}" if topic else ""
    raw = f"mcq:{concept_id}:{question}:{answer}{topic_part}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def generate_teach_card(concept_id: str, topic: str | None = None) -> str:
    """Generate themed teach content via GPT, or return static content as fallback."""
    concepts = load_concepts()
    concept = concepts.get(concept_id)
    if concept is None:
        return ""

    static_content = concept.teach_content or ""

    if not topic or not ai_available():
        return static_content

    client = _get_client()
    if client is None:
        return static_content

    try:
        teach_sys = prompt_config.get("teach_system", "")
        if not teach_sys:
            teach_sys = (
                "You are a friendly Spanish language teacher. "
                "Create a brief, engaging teach card (2-4 paragraphs in markdown) "
                "that explains the grammar concept using examples themed around the given topic. "
                "Keep it A1-level appropriate."
            )

        response = client.chat.completions.create(
            model=prompt_config.get_model("teach"),
            messages=[
                {
                    "role": "system",
                    "content": teach_sys,
                },
                {
                    "role": "user",
                    "content": (
                        f"Concept: {concept.name}\n"
                        f"Description: {concept.description}\n"
                        f"Original teach content:\n{static_content}\n\n"
                        f"Theme: {topic}\n\n"
                        f"Rewrite the teach content with examples themed around '{topic}'."
                    ),
                },
            ],
            temperature=prompt_config.get_temperature("teach"),
            max_tokens=1000,
        )
        content = response.choices[0].message.content or ""
        return content.strip() if content.strip() else static_content
    except Exception:
        return static_content


def generate_conversation_opener(concept_id: str, topic: str, difficulty: int = 1) -> str:
    """Generate a 1-2 sentence conversation starter in Spanish themed to topic."""
    if not ai_available():
        return ""

    client = _get_client()
    if client is None:
        return ""

    concepts = load_concepts()
    concept = concepts.get(concept_id)
    concept_name = concept.name if concept else concept_id

    difficulty_label = {1: "simple A1", 2: "A1-A2", 3: "A2"}.get(difficulty, "A1")

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a Spanish conversation partner. "
                        "Generate a single conversation opener (1-2 sentences) in Spanish "
                        "that naturally uses the given grammar concept and is themed around the topic. "
                        "Return ONLY the Spanish sentence(s), nothing else."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Grammar concept: {concept_name}\n"
                        f"Topic: {topic}\n"
                        f"Difficulty: {difficulty_label}\n"
                    ),
                },
            ],
            temperature=0.9,
            max_tokens=200,
        )
        return (response.choices[0].message.content or "").strip()
    except Exception:
        return ""


def generate_story_card(
    concept_id: str,
    topic: str,
    difficulty: int,
    persona_prompt: str,
    persona_name: str,
) -> dict[str, Any]:
    """Generate a short Spanish story and comprehension MCQs."""
    concepts = load_concepts()
    concept = concepts.get(concept_id)
    concept_name = concept.name if concept else concept_id

    fallback_story = (
        f"Ayer {persona_name} habló sobre {topic}. "
        f"Primero practicó {concept_name}. "
        f"Luego tomó un café y siguió estudiando. "
        f"Al final, dijo que fue un buen día."
    )
    fallback_questions = [
        {
            "question": f"¿De qué habló {persona_name}?",
            "correct_answer": f"De {topic}",
            "options": [f"De {topic}", "De medicina", "De política", "De dinero"],
        },
        {
            "question": "¿Qué hizo al final?",
            "correct_answer": "Dijo que fue un buen día",
            "options": [
                "Dijo que fue un buen día",
                "Se fue al hospital",
                "Perdió el tren",
                "Canceló todo",
            ],
        },
    ]

    if not ai_available():
        return {"story": fallback_story, "questions": fallback_questions}

    client = _get_client()
    if client is None:
        return {"story": fallback_story, "questions": fallback_questions}

    try:
        story_sys = prompt_config.get("story_system", "")
        if not story_sys:
            story_sys = (
                "You create Spanish reading-comprehension micro stories for beginners. "
                "Return STRICT JSON only."
            )

        response = client.chat.completions.create(
            model=prompt_config.get_model("story"),
            messages=[
                {
                    "role": "system",
                    "content": story_sys,
                },
                {
                    "role": "user",
                    "content": (
                        f"Persona name: {persona_name}\n"
                        f"Persona style:\n{persona_prompt}\n---\n"
                        f"Topic: {topic}\n"
                        f"Target concept: {concept_name} ({concept_id})\n"
                        f"Difficulty: {difficulty}\n\n"
                        "Create a story card as JSON with keys: story (3-5 Spanish sentences) and questions (2-3 items). "
                        "Each question must have question, correct_answer, options (4 total including correct_answer). "
                        "A1: simple literal questions. A2: can include one mild inference question."
                    ),
                },
            ],
            temperature=prompt_config.get_temperature("story"),
            max_tokens=1000,
            response_format={"type": "json_object"},
        )
        content = (response.choices[0].message.content or "").strip()
        payload = json.loads(content)
        story = str(payload.get("story") or "").strip()
        questions_raw = payload.get("questions")
        if not story or not isinstance(questions_raw, list):
            return {"story": fallback_story, "questions": fallback_questions}

        questions: list[dict[str, Any]] = []
        for item in questions_raw[:3]:
            if not isinstance(item, dict):
                continue
            question = str(item.get("question") or "").strip()
            correct = str(item.get("correct_answer") or "").strip()
            options_raw = item.get("options")
            if not question or not correct or not isinstance(options_raw, list):
                continue
            options = [str(opt).strip() for opt in options_raw if str(opt).strip()]
            if correct not in options:
                options.append(correct)
            deduped: list[str] = []
            for opt in options:
                if opt not in deduped:
                    deduped.append(opt)
            if len(deduped) < 4:
                for extra in ["No se menciona", "No está claro", "Otra opción"]:
                    if extra not in deduped:
                        deduped.append(extra)
                    if len(deduped) >= 4:
                        break
            questions.append(
                {
                    "question": question,
                    "correct_answer": correct,
                    "options": deduped[:4],
                }
            )

        if not questions:
            return {"story": fallback_story, "questions": fallback_questions}
        return {"story": story, "questions": questions}
    except Exception:
        return {"story": fallback_story, "questions": fallback_questions}


__all__ = [
    "ai_available",
    "convert_existing_cards_to_mcq",
    "ensure_cache_populated",
    "generate_conversation_opener",
    "generate_mcq_batch",
    "generate_story_card",
    "generate_teach_card",
    "prefetch_next_concepts",
]
