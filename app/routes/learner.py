"""Learner routes: stats API and translate."""

import json

import anthropic
from fastapi import APIRouter, Form
from fastapi.responses import JSONResponse

from ..config import LEARNER_ID, TRANSLATE_MODEL
from ..database import (
    get_all_words,
    get_grammar_status,
    get_or_create_learner,
    get_words_due,
)

router = APIRouter()

_client = anthropic.Anthropic()
_translate_cache: dict[str, str] = {}


@router.get("/learner/stats")
def learner_stats():
    """JSON summary of the learner's profile, grammar, and word tracking."""
    profile = get_or_create_learner(LEARNER_ID)
    grammar = get_grammar_status(LEARNER_ID)
    words = get_all_words(LEARNER_ID)
    due = get_words_due(LEARNER_ID)

    interests = None
    if profile.get("interests"):
        try:
            interests = json.loads(profile["interests"])
        except (json.JSONDecodeError, TypeError):
            interests = None

    return JSONResponse(
        {
            "learner_id": LEARNER_ID,
            "profile": {
                "display_name": profile.get("display_name"),
                "cefr_level": profile.get("cefr_level"),
                "interests": interests,
                "created_at": str(profile.get("created_at", "")),
                "updated_at": str(profile.get("updated_at", "")),
            },
            "grammar": {
                topic: {
                    "status": info["status"],
                    "last_tested": info["last_tested"],
                    "evidence_count": len(info["evidence"]),
                }
                for topic, info in grammar.items()
            },
            "vocabulary": {
                "total_words": len(words),
                "words_due": len(due),
                "due_words": [
                    {"word": w["word"], "translation": w["translation"]} for w in due
                ],
            },
            "word_details": [
                {
                    "word": w["word"],
                    "translation": w["translation"],
                    "domain": w["domain"],
                    "repetitions": w["repetitions"],
                    "ease_factor": round(w["ease_factor"], 2),
                    "interval_days": round(w["interval_days"], 1),
                    "times_correct": w["times_correct"],
                    "times_wrong": w["times_wrong"],
                    "next_review": w["next_review"],
                }
                for w in words
            ],
        }
    )


@router.post("/translate")
def translate(text: str = Form(...), context: str = Form("")):
    text = text.strip()
    if not text:
        return {"translation": ""}
    cache_key = f"{text}|||{context}"
    if cache_key in _translate_cache:
        return {"translation": _translate_cache[cache_key]}
    resp = _client.messages.create(
        model=TRANSLATE_MODEL,
        max_tokens=100,
        messages=[
            {
                "role": "user",
                "content": (
                    "Translate this Spanish to English. Reply with ONLY the "
                    "English translation, nothing else. Be brief.\n\n"
                    f"Spanish: {text}"
                    + (f"\nSentence context: {context}" if context else "")
                ),
            }
        ],
    )
    translation = resp.content[0].text.strip()
    _translate_cache[cache_key] = translation
    return {"translation": translation}
