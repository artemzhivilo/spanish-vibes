"""Persona loader — loads conversation personas from YAML."""

from __future__ import annotations

import random
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List

import yaml

from .db import DATA_DIR, _open_connection, consume_dev_override, get_current_user_id
from .conversation import MARTA_PERSONA

PERSONAS_DIR = DATA_DIR / "personas"


@dataclass(slots=True)
class Persona:
    id: str
    name: str
    system_prompt: str
    age: int | None = None
    location: str | None = None
    occupation: str | None = None


_PERSONA_CACHE: Dict[str, Persona] | None = None


def _load_yaml_personas() -> Dict[str, Persona]:
    personas: Dict[str, Persona] = {}
    if not PERSONAS_DIR.exists():
        return personas
    for path in PERSONAS_DIR.glob("*.yaml"):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:
            continue
        persona_id = str(data.get("yamlid") or data.get("id") or path.stem)
        system_prompt = str(data.get("system_prompt") or "").strip()
        if not persona_id or not system_prompt:
            continue
        personas[persona_id] = Persona(
            id=persona_id,
            name=str(data.get("name") or persona_id.title()),
            system_prompt=system_prompt,
            age=data.get("age"),
            location=data.get("location"),
            occupation=data.get("occupation"),
        )
    return personas


def load_all_personas() -> List[Persona]:
    global _PERSONA_CACHE
    if _PERSONA_CACHE is None:
        _PERSONA_CACHE = _load_yaml_personas()
    if not _PERSONA_CACHE:
        fallback = Persona(
            id="marta_fallback", name="Marta", system_prompt=MARTA_PERSONA
        )
        _PERSONA_CACHE = {fallback.id: fallback}
    return list(_PERSONA_CACHE.values())


def load_persona(persona_id: str | None) -> Persona:
    if not persona_id:
        return Persona(id="marta_fallback", name="Marta", system_prompt=MARTA_PERSONA)
    all_personas = {p.id: p for p in load_all_personas()}
    return all_personas.get(persona_id) or Persona(
        id="marta_fallback", name="Marta", system_prompt=MARTA_PERSONA
    )


def select_persona(exclude_id: str | None = None) -> Persona:
    personas = load_all_personas()
    if not personas:
        return Persona(id="marta_fallback", name="Marta", system_prompt=MARTA_PERSONA)
    candidates = [p for p in personas if p.id != exclude_id] or personas

    forced_persona_id = consume_dev_override("force_next_persona")
    if forced_persona_id:
        forced = next((p for p in candidates if p.id == forced_persona_id), None)
        if forced is not None:
            return forced

    try:
        engagement_by_persona = _load_persona_engagement()
    except sqlite3.Error:
        return random.choice(candidates)

    weights: list[float] = []
    for persona in candidates:
        metrics = engagement_by_persona.get(persona.id)
        engagement_affinity = float(metrics["avg_enjoyment_score"]) if metrics else 0.5
        novelty_bonus = _compute_novelty_bonus(
            str(metrics.get("last_conversation_at")) if metrics else None,
            int(metrics.get("conversation_count") or 0) if metrics else 0,
        )
        random_explore = random.random()
        score = engagement_affinity * 0.6 + novelty_bonus * 0.3 + random_explore * 0.1
        weights.append(max(0.01, score))

    if not weights or sum(weights) <= 0:
        return random.choice(candidates)
    return random.choices(candidates, weights=weights, k=1)[0]


def _load_persona_engagement() -> dict[str, dict[str, object]]:
    user_id = get_current_user_id()
    with _open_connection() as conn:
        rows = conn.execute(
            """
            SELECT persona_id, conversation_count, avg_enjoyment_score, last_conversation_at
            FROM persona_engagement
            WHERE user_id = ? AND topic_id IS NULL
            """,
            (user_id,),
        ).fetchall()
    return {str(row["persona_id"]): dict(row) for row in rows}


def _compute_novelty_bonus(
    last_conversation_at: str | None, conversation_count: int
) -> float:
    if conversation_count <= 0 or not last_conversation_at:
        return 1.0
    try:
        last_dt = datetime.fromisoformat(last_conversation_at)
    except ValueError:
        return 1.0
    if last_dt.tzinfo is None:
        last_dt = last_dt.replace(tzinfo=timezone.utc)
    now_dt = datetime.now(timezone.utc)
    days_since = max(0.0, (now_dt - last_dt).total_seconds() / 86400.0)
    return min(1.0, days_since / 5.0)


def get_persona_prompt(
    persona: Persona | None,
    persona_memories: list[str] | None = None,
    user_facts: list[str] | None = None,
) -> str:
    base_prompt = (
        persona.system_prompt if persona and persona.system_prompt else MARTA_PERSONA
    )
    sections = [base_prompt]

    if persona_memories:
        memory_block = "\n".join(f"- {memory}" for memory in persona_memories)
        sections.append(
            "THINGS YOU REMEMBER FROM PAST CONVERSATIONS:\n"
            f"{memory_block}\n"
            "Use these naturally in conversation; reference them when relevant without forcing callbacks."
        )

    if user_facts:
        facts_block = "\n".join(f"- {fact}" for fact in user_facts)
        sections.append(
            "WHAT YOU KNOW ABOUT THE LEARNER:\n"
            f"{facts_block}\n"
            "All personas know these facts. Use them naturally to make conversation feel personal."
        )

    return "\n\n".join(sections)
