"""Conversation card engine — AI-driven mini-conversations in Spanish.

By default the AI partner is "Marta", but callers can swap in any persona by
passing a custom system prompt. Uses a single LLM call per user turn
(respond_to_user) that combines evaluation, reply, and steering into one
structured output.
"""

from __future__ import annotations

import json
import random
from difflib import SequenceMatcher
import re
from dataclasses import dataclass, field
from typing import Any, Literal

from .flow_ai import ai_available, _get_client
from .concepts import load_concepts
from . import prompts as prompt_config


# ── Default Marta persona ───────────────────────────────────────────────────
# Loaded from data/prompts.yaml — edit there to change.

def _get_default_persona() -> str:
    return prompt_config.get("default_persona", _MARTA_PERSONA_FALLBACK)

# Hard-coded fallback in case YAML is missing/broken
_MARTA_PERSONA_FALLBACK = """
You are Marta, a 25-year-old university student from Madrid studying
journalism. You're warm, curious, and a little bit sarcastic (but never
mean). You love music, cooking, and debating about movies. You're
chatting with a friend who's learning Spanish.

PERSONALITY RULES:
- Use informal tú, never usted
- React genuinely — show surprise, agreement, curiosity
- Share brief opinions of your own (1 sentence max) to keep it natural
- Use casual filler words occasionally: "bueno", "pues", "a ver"
- Never say "you made a mistake" or break character to teach
- You're a friend first, language helper second
""".strip()

# Keep MARTA_PERSONA as a property for backward compat with personas.py
MARTA_PERSONA = _MARTA_PERSONA_FALLBACK


# ── Scaffolding rules by difficulty ──────────────────────────────────────────
# Loaded from data/prompts.yaml — edit there to change.

def _get_scaffolding(difficulty: int) -> str:
    return prompt_config.get_scaffolding(difficulty) or SCAFFOLDING_RULES.get(difficulty, SCAFFOLDING_RULES[1])

# Hard-coded fallback
SCAFFOLDING_RULES: dict[int, str] = {
    1: """
SCAFFOLDING (A1 - Maximum support):
- If the learner seems stuck (short response, English words, "???"),
  provide a hint with a partial sentence structure
- Use simple, high-frequency vocabulary only
- It's okay to include a brief English translation in parentheses
  for one key word per response
- Keep your sentences SHORT (under 10 words each)
- Ask yes/no or either/or questions to reduce cognitive load
  Example: "¿Comiste pizza O pasta?" instead of "¿Qué comiste?"
""".strip(),
    2: """
SCAFFOLDING (A1-A2 - Moderate support):
- Only help if the learner explicitly asks or seems confused
- No English translations
- Use vocabulary appropriate for upper-beginner
- Ask open-ended questions but keep them focused
  Example: "¿Qué hiciste?" not "Cuéntame todo sobre tu fin de semana"
""".strip(),
    3: """
SCAFFOLDING (A2 - Minimal support):
- No hints, no English, no simplification
- Use natural vocabulary and sentence structures
- Challenge with slightly more complex follow-ups
- Ask questions that require extended responses
  Example: "¿Qué fue lo más interesante de tu viaje?"
""".strip(),
}


# ── Concept steering hints ──────────────────────────────────────────────────

CONCEPT_STEERING: dict[str, str] = {
    "preterite": "Ask about completed past actions: what they did, where they went, what happened. Questions like '¿Qué hiciste...?' or '¿Adónde fuiste...?'",
    "imperfect": "Ask about childhood memories, habitual past actions, descriptions of how things used to be. '¿Qué hacías cuando eras niño?' or '¿Cómo era tu escuela?'",
    "present_perfect": "Ask about recent experiences or life experiences: '¿Has viajado a España?' '¿Qué has comido hoy?' '¿Has visto esa película?'",
    "present": "Ask about daily routines, habits, current states. Questions like '¿Qué haces normalmente...?' or '¿Cómo es tu día típico?'",
    "ser_estar": "Ask questions that require describing states (estar) vs identity/characteristics (ser). Mix both: '¿Cómo es tu ciudad?' and '¿Cómo estás hoy?'",
    "gustar": "Ask about preferences, likes/dislikes. '¿Qué tipo de música te gusta?' or '¿Te gustan los deportes?'",
    "subjunctive": "Create scenarios requiring wishes, recommendations, or doubts. '¿Qué le recomiendas a tu amigo?' or 'Espero que...'",
    "imperative": "Create scenarios requiring commands or instructions. '¿Cómo se prepara tu comida favorita?' (recipe = commands)",
    "future": "Ask about plans, predictions, intentions. '¿Qué vas a hacer este fin de semana?' or '¿Cómo crees que será el futuro?'",
    "reflexive": "Ask about daily routines involving reflexive verbs. '¿A qué hora te levantas?' or '¿Cómo te preparas por la mañana?'",
    "greetings": "Practice greetings, introductions, and small talk. '¿Cómo estás?' '¿De dónde eres?' '¿Qué haces?'",
    "articles": "Ask questions requiring articles: '¿Cuál es el libro que más te gusta?' '¿Tienes una mascota?'",
    "adjective": "Ask descriptive questions: '¿Cómo es tu mejor amigo?' '¿Cómo fue la película?'",
    "possessive": "Ask about belongings and relationships: '¿Dónde está tu casa?' '¿Cómo se llama tu hermano?'",
    "demonstratives": "Ask questions requiring this/that: '¿Te gusta este libro o ese?' '¿Quién es aquella chica?'",
    "plurals": "Ask questions requiring plural nouns and articles: '¿Cuántos hermanos tienes?' '¿Qué ciudades conoces?'",
    "weather": "Ask about weather and seasons: '¿Qué tiempo hace hoy?' '¿Cuál es tu estación favorita?'",
    "tener_que": "Ask about obligations and responsibilities: '¿Qué tienes que hacer hoy?' '¿Qué hay que hacer para aprender español?'",
    "gerund": "Ask about what someone is doing right now: '¿Qué estás haciendo?' '¿Qué está pasando?'",
    "poder": "Ask about abilities and possibilities: '¿Qué puedes hacer bien?' '¿Puedes cocinar?'",
    "comparativ": "Ask questions requiring comparisons: '¿Qué es más divertido, el cine o la playa?' '¿Quién es mayor, tú o tu hermano?'",
    "por_para": "Ask questions that require por or para: '¿Para qué estudias español?' '¿Por dónde caminas?'",
    "conjunct": "Create scenarios requiring linking sentences: '¿Por qué te gusta...?' (porque) or '¿Qué haces cuando...?' (cuando)",
    "conditional": "Create polite request scenarios: '¿Qué te gustaría hacer?' 'Imagine you're at a restaurant — ask politely.'",
    "direct_object": "Ask questions where the learner needs to replace a noun with lo/la/los/las: '¿Tienes el libro?' → 'Sí, lo tengo.'",
    "indirect_object": "Ask about giving, telling, showing: '¿Qué le dices a tu amigo?' '¿Qué me recomiendas?'",
    "shopping": "Create a shopping scenario: '¿Cuánto cuesta?' '¿Qué quieres comprar?'",
    "health": "Ask about health: '¿Cómo te sientes?' '¿Qué te duele?'",
    "travel": "Ask about trips and transport: '¿Cómo viajas?' '¿Adónde quieres ir?'",
    "hobbies": "Ask about free time activities: '¿Qué te gusta hacer los fines de semana?'",
    "house": "Ask about home and rooms: '¿Cómo es tu casa?' '¿Cuántas habitaciones tiene?'",
    "city": "Ask about cities and neighborhoods: '¿Cómo es tu ciudad?' '¿Qué hay cerca de tu casa?'",
    "profes": "Ask about jobs and work: '¿A qué te dedicas?' '¿Qué quieres ser?'",
    "frequency": "Ask about how often someone does things: '¿Con qué frecuencia...?' '¿Siempre desayunas?'",
    "muy_mucho": "Ask questions that require muy or mucho: '¿Es muy grande tu ciudad?' '¿Comes mucho?'",
}


_SPANISH_MARKERS = {
    "el", "la", "los", "las", "un", "una", "de", "en", "que", "es",
    "yo", "tú", "tu", "él", "ella", "nosotros", "muy", "pero", "como",
    "por", "para", "con", "sin", "más", "también", "ser", "estar",
    "hoy", "ayer", "mañana", "sí", "no", "bien", "mal", "aquí", "fui",
    "tienda",
}

_ENGLISH_MARKERS = {
    "the", "is", "are", "was", "were", "have", "has", "had",
    "do", "does", "did", "will", "would", "could", "should",
    "i", "you", "he", "she", "we", "they", "my", "your",
    "this", "that", "these", "those", "with", "from", "about",
}

_LANGUAGE_WORD_RE = re.compile(r"[a-záéíóúñü]+", re.IGNORECASE)
_TOKEN_SPLIT_RE = re.compile(r"[A-Za-zÁÉÍÓÚÜáéíóúñÑ']+|[¿¡.,!?;:]")


def get_concept_steering(concept_id: str) -> str:
    """Get steering hint for a concept, with partial-match fallback."""
    for key, hint in CONCEPT_STEERING.items():
        if key in concept_id.lower():
            return hint
    return "Ask follow-up questions that naturally require the target grammar structure in the response."


# ── Fallback topics for cold start ──────────────────────────────────────────

_FALLBACK_TOPICS = [
    "deportes", "música", "comida", "viajes", "tecnología",
    "películas", "naturaleza", "arte", "historia", "moda",
]


def get_random_topic(exclude: str | None = None) -> str:
    """Pick a random topic from seeded interest_topics, falling back to built-in list."""
    from .db import get_all_interest_topics
    topics = get_all_interest_topics()
    names = [t["name"] for t in topics if t.get("name")]
    if not names:
        names = list(_FALLBACK_TOPICS)
    if exclude and len(names) > 1:
        names = [n for n in names if n != exclude]
    return random.choice(names) if names else "la vida diaria"


# ── Dataclasses ──────────────────────────────────────────────────────────────

@dataclass(slots=True)
class Correction:
    """A single grammar correction from the user's message."""

    original: str
    corrected: str
    explanation: str
    concept_id: str


@dataclass(slots=True)
class ConversationMessage:
    """A single message in the conversation."""

    role: Literal["ai", "user", "system"]
    content: str
    corrections: list[Correction] | None = None
    timestamp: str = ""
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        msg: dict[str, Any] = {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
        }
        if self.corrections:
            msg["corrections"] = [
                {
                    "original": c.original,
                    "corrected": c.corrected,
                    "explanation": c.explanation,
                    "concept_id": c.concept_id,
                }
                for c in self.corrections
            ]
        if self.metadata:
            msg["metadata"] = self.metadata
        return msg

    @staticmethod
    def from_dict(data: dict[str, Any]) -> ConversationMessage:
        corrections = None
        if data.get("corrections"):
            corrections = [
                Correction(
                    original=c["original"],
                    corrected=c["corrected"],
                    explanation=c["explanation"],
                    concept_id=c["concept_id"],
                )
                for c in data["corrections"]
            ]
        return ConversationMessage(
            role=data["role"],
            content=data["content"],
            corrections=corrections,
            timestamp=data.get("timestamp", ""),
            metadata=data.get("metadata"),
        )


@dataclass(slots=True)
class RespondResult:
    """Combined evaluation + reply from a single LLM call."""

    ai_reply: str
    corrections: list[Correction]
    is_grammatically_correct: bool
    should_continue: bool
    hint: str | None


@dataclass(slots=True)
class VocabularyGap:
    english_word: str
    spanish_word: str
    concept_id: str | None = None


@dataclass(slots=True)
class EnglishFallbackResult:
    original_english: str
    spanish_translation: str
    vocabulary_gaps: list[VocabularyGap]
    display_message: str


# Keep for backwards compat — deprecated
@dataclass(slots=True)
class EvaluationResult:
    """Deprecated: use RespondResult via respond_to_user instead."""

    corrections: list[Correction]
    is_grammatically_correct: bool
    recast: str


@dataclass(slots=True)
class ConversationSummary:
    """Post-conversation summary with corrections and score."""

    corrections: list[Correction]
    concepts_practiced: list[str]
    turn_count: int
    score: float  # 0.0 - 1.0 based on accuracy


@dataclass(slots=True)
class ConversationCard:
    """A conversation card in the flow feed."""

    topic: str
    concept: str
    difficulty: int
    opener: str
    max_turns: int = 4
    messages: list[ConversationMessage] = field(default_factory=list)
    persona_name: str = "Marta"

    @property
    def turn_count(self) -> int:
        return len(self.messages)

    @property
    def user_turn_count(self) -> int:
        return sum(1 for m in self.messages if m.role == "user")


def _detect_language(text: str) -> str:
    """Simple heuristic: return 'es', 'en', or 'mixed'."""
    lower = text.lower()
    tokens = {match.group(0) for match in _LANGUAGE_WORD_RE.finditer(lower)}
    es_count = len(tokens & _SPANISH_MARKERS)
    en_count = len(tokens & _ENGLISH_MARKERS)
    if en_count == 0 and es_count == 0:
        return "es"
    if en_count == 0:
        return "es"
    if es_count == 0:
        return "en" if en_count >= 2 else "es"
    if abs(en_count - es_count) <= 1:
        return "mixed"
    return "en" if en_count > es_count else "es"


def _tokenize_for_diff(text: str) -> list[str]:
    tokens = _TOKEN_SPLIT_RE.findall(text)
    if not tokens:
        tokens = text.split()
    return [token for token in tokens if token]


def _format_segment(tokens: list[str]) -> str:
    if not tokens:
        return ""
    text = " ".join(tokens).strip()
    text = re.sub(r"\s+([.,!?;:])", r"\1", text)
    text = text.replace("¿ ", "¿").replace("¡ ", "¡")
    return text


def _normalize_chip_text(text: str) -> str:
    cleaned = text.strip().strip("¡!¿?,.;:")
    return cleaned or text.strip()


def _explode_corrections(corrections: list[Correction]) -> list[Correction]:
    exploded: list[Correction] = []
    for corr in corrections:
        original = corr.original.strip()
        corrected = corr.corrected.strip()
        if not original and not corrected:
            continue
        tokens_orig = _tokenize_for_diff(original)
        tokens_new = _tokenize_for_diff(corrected)
        matcher = SequenceMatcher(None, tokens_orig, tokens_new)
        segments: list[Correction] = []
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "equal":
                continue
            orig_tokens = tokens_orig[i1:i2]
            new_tokens = tokens_new[j1:j2]
            # Provide a bit of context for single-word swaps like articles
            if (
                tag == "replace"
                and i2 - i1 == 1
                and j2 - j1 == 1
                and i1 > 0
                and j1 > 0
            ):
                prev_orig = tokens_orig[i1 - 1]
                prev_new = tokens_new[j1 - 1]
                if prev_orig == prev_new:
                    orig_tokens = tokens_orig[i1 - 1 : i2]
                    new_tokens = tokens_new[j1 - 1 : j2]

            orig_segment = _normalize_chip_text(_format_segment(orig_tokens))
            new_segment = _normalize_chip_text(_format_segment(new_tokens))
            if not orig_segment and not new_segment:
                continue
            segments.append(
                Correction(
                    original=orig_segment or "∅",
                    corrected=new_segment or "∅",
                    explanation=corr.explanation,
                    concept_id=corr.concept_id,
                )
            )
        exploded.extend(segments or [corr])
    return exploded


# ── CEFR difficulty mapping ──────────────────────────────────────────────────

_DIFFICULTY_TO_CEFR = {1: "A1", 2: "A2", 3: "A2-B1"}


# ── Conversation Engine ─────────────────────────────────────────────────────

class ConversationEngine:
    """Drives conversation cards: opener, respond_to_user, summary."""

    def generate_opener(
        self,
        topic: str,
        concept: str,
        difficulty: int = 1,
        persona_prompt: str | None = None,
        persona_name: str = "Marta",
    ) -> str:
        """Create a conversation starter for the selected persona."""
        if not ai_available():
            return self._fallback_opener(topic, concept, difficulty)

        client = _get_client()
        if client is None:
            return self._fallback_opener(topic, concept, difficulty)

        cefr = _DIFFICULTY_TO_CEFR.get(difficulty, "A1")
        concept_name = self._resolve_concept_name(concept)
        steering = get_concept_steering(concept)
        persona_block = persona_prompt or _get_default_persona()

        opener_template = prompt_config.get("opener_system", "")
        if opener_template:
            system_content = opener_template.format(
                persona_block=persona_block,
                persona_name=persona_name,
                concept_name=concept_name,
                steering=steering,
                topic=topic,
                cefr=cefr,
            )
        else:
            # Fallback if YAML is missing
            system_content = (
                f"{persona_block}\n\n"
                f"Generate a conversation opener as {persona_name}. 1-2 sentences in Spanish.\n"
                f"The opener MUST ask a question that REQUIRES the learner to respond "
                f"using {concept_name}.\n\n"
                f"STEERING: {steering}\n\n"
                f"Topic: {topic}\n"
                f"Difficulty: {cefr}\n\n"
                "RULES:\n"
                "- Write ONLY in Spanish\n"
                f"- Keep it {cefr}-appropriate\n"
                "- Ask a question that requires the target grammar in the answer\n"
                "- Return ONLY the Spanish text, nothing else"
            )

        try:
            response = client.chat.completions.create(
                model=prompt_config.get_model("opener"),
                messages=[
                    {
                        "role": "system",
                        "content": system_content,
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Topic: {topic}\n"
                            f"Grammar concept: {concept_name}\n"
                            f"Generate the opener as {persona_name}."
                        ),
                    },
                ],
                temperature=prompt_config.get_temperature("opener"),
                max_tokens=150,
            )
            content = (response.choices[0].message.content or "").strip()
            return content if content else self._fallback_opener(topic, concept, difficulty)
        except Exception:
            return self._fallback_opener(topic, concept, difficulty)

    def detect_and_handle_english(
        self,
        user_text: str,
        concept: str,
        difficulty: int,
    ) -> EnglishFallbackResult | None:
        """Detect English input, translate it, and surface vocabulary gaps."""
        if not user_text.strip():
            return None
        language = _detect_language(user_text)
        if language == "es":
            return None
        if not ai_available():
            return None
        client = _get_client()
        if client is None:
            return None

        cefr = _DIFFICULTY_TO_CEFR.get(difficulty, "A1")
        concept_name = self._resolve_concept_name(concept)

        sys_template = prompt_config.get("english_fallback_system", "")
        if sys_template:
            system_prompt = sys_template.format(cefr=cefr, concept_name=concept_name)
        else:
            system_prompt = (
                "You help beginner Spanish learners stay in Spanish conversations.\n"
                "The learner replied in ENGLISH or mixed language.\n"
                "You must translate their intent to natural Spanish and identify vocabulary gaps.\n"
                "Return STRICT JSON with keys: spanish_translation, vocabulary_gaps, encouragement.\n"
                "Each vocabulary gap is an object with 'english' and 'spanish'.\n"
                "Level: " + cefr + ", Target concept: " + concept_name + "."
            )

        usr_template = prompt_config.get("english_fallback_user", "")
        if usr_template:
            user_instruction = usr_template.format(user_text=user_text.strip())
        else:
            user_instruction = (
                "The learner typed this in English during a Spanish conversation:\n"
                f"{user_text.strip()}\n\n"
                "1. Translate their message to natural Spanish at the target level.\n"
                "2. List specific English words/phrases they didn't know in Spanish.\n"
                "3. Provide a friendly encouragement message.\n"
                "Return JSON: {\"spanish_translation\": str, \"vocabulary_gaps\": [{\"english\": str, \"spanish\": str}], \"encouragement\": str}"
            )

        try:
            response = client.chat.completions.create(
                model=prompt_config.get_model("english_fallback"),
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_instruction},
                ],
                temperature=prompt_config.get_temperature("english_fallback"),
                max_tokens=400,
            )
        except Exception:
            return None

        content = (response.choices[0].message.content or "").strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[-1]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()

        try:
            payload: dict[str, Any] = json.loads(content)
        except json.JSONDecodeError:
            return None

        translation = (payload.get("spanish_translation") or "").strip()
        if not translation:
            return None
        encouragement = (payload.get("encouragement") or "").strip()
        vocab_entries = payload.get("vocabulary_gaps") or []
        vocabulary_gaps: list[VocabularyGap] = []
        for entry in vocab_entries:
            if not isinstance(entry, dict):
                continue
            english = (entry.get("english") or entry.get("english_word") or "").strip()
            spanish = (entry.get("spanish") or entry.get("spanish_word") or "").strip()
            if english and spanish:
                vocabulary_gaps.append(
                    VocabularyGap(
                        english_word=english,
                        spanish_word=spanish,
                        concept_id=concept or None,
                    )
                )

        lines: list[str] = []
        if encouragement:
            lines.append(encouragement)
        lines.append(f"💡 En español: {translation}")
        if vocabulary_gaps:
            vocab_text = ", ".join(f"{gap.english_word} → {gap.spanish_word}" for gap in vocabulary_gaps)
            lines.append(f"📝 Vocabulario nuevo: {vocab_text}")

        display_message = "\n".join(lines)
        return EnglishFallbackResult(
            original_english=user_text.strip(),
            spanish_translation=translation,
            vocabulary_gaps=vocabulary_gaps,
            display_message=display_message,
        )

    def respond_to_user(
        self,
        messages: list[ConversationMessage],
        user_text: str,
        topic: str,
        concept: str,
        difficulty: int = 1,
        persona_prompt: str | None = None,
        persona_name: str = "Marta",
    ) -> RespondResult:
        """Single LLM call: evaluate grammar, generate persona reply with recast,
        decide if conversation should continue, and optionally provide a hint."""
        if not ai_available():
            return self._fallback_respond(topic, user_text, messages)

        client = _get_client()
        if client is None:
            return self._fallback_respond(topic, user_text, messages)

        cefr = _DIFFICULTY_TO_CEFR.get(difficulty, "A1")
        concept_name = self._resolve_concept_name(concept)
        steering = get_concept_steering(concept)
        scaffolding = _get_scaffolding(difficulty)
        user_turns = sum(1 for m in messages if m.role == "user")
        turn_number = user_turns + 1  # counting the current user_text

        persona_block = persona_prompt or _get_default_persona()

        respond_template = prompt_config.get("respond_system", "")
        if respond_template:
            system_prompt = respond_template.format(
                persona_block=persona_block,
                cefr=cefr,
                concept_name=concept_name,
                topic=topic,
                turn_number=turn_number,
                persona_name=persona_name,
                steering=steering,
                scaffolding=scaffolding,
            )
        else:
            # Hard-coded fallback (should never hit if YAML exists)
            system_prompt = (
                f"{persona_block}\n\n"
                f"CURRENT CONVERSATION CONTEXT:\n"
                f"- Learner level: {cefr}\n"
                f"- Grammar target: {concept_name}\n"
                f"- Topic: {topic}\n"
                f"- Conversation turn: {turn_number} of ~4\n\n"
                "YOUR TASK:\n"
                "Read the learner's last message and do THREE things simultaneously:\n\n"
                f"1. EVALUATE: Check their Spanish for grammar errors, focusing on "
                f"{concept_name}.\n\n"
                f"2. REPLY: Write your conversational response as {persona_name}. 1-2 sentences "
                "in Spanish.\n\n"
                "3. STEER: Include a follow-up question.\n\n"
                f"CONCEPT STEERING: {steering}\n\n"
                f"{scaffolding}\n\n"
                "Return ONLY valid JSON with keys: reply, corrections, is_correct, should_continue, hint."
            )

        # Build chat history
        chat_messages: list[dict[str, str]] = [
            {"role": "system", "content": system_prompt},
        ]
        for msg in messages:
            role = "assistant" if msg.role == "ai" else "user"
            chat_messages.append({"role": role, "content": msg.content})
        # Add the current user message
        chat_messages.append({"role": "user", "content": user_text})

        try:
            response = client.chat.completions.create(
                model=prompt_config.get_model("respond"),
                messages=chat_messages,
                temperature=prompt_config.get_temperature("respond"),
                max_tokens=500,
                response_format={"type": "json_object"},
            )
            content = (response.choices[0].message.content or "").strip()
            # Strip markdown fences if present
            if content.startswith("```"):
                content = content.split("\n", 1)[-1]
                if content.endswith("```"):
                    content = content[:-3]
                content = content.strip()

            data = json.loads(content)

            corrections = [
                Correction(
                    original=c.get("original", ""),
                    corrected=c.get("corrected", ""),
                    explanation=c.get("explanation", ""),
                    concept_id=c.get("concept_id", concept),
                )
                for c in data.get("corrections", [])
                if c.get("original") and c.get("corrected")
            ]
            corrections = _explode_corrections(corrections)

            ai_reply = str(data.get("reply", ""))
            if not ai_reply:
                ai_reply = self._fallback_reply(topic)

            return RespondResult(
                ai_reply=ai_reply,
                corrections=corrections,
                is_grammatically_correct=bool(data.get("is_correct", True)),
                should_continue=bool(data.get("should_continue", True)),
                hint=data.get("hint") if difficulty == 1 else None,
            )
        except Exception:
            return self._fallback_respond(topic, user_text, messages)

    # ── Deprecated methods (kept for backwards compat) ───────────────────

    def evaluate_response(
        self,
        user_text: str,
        concept: str,
        difficulty: int = 1,
    ) -> EvaluationResult:
        """Standalone grammar evaluation for legacy callers."""
        if not ai_available():
            return EvaluationResult(corrections=[], is_grammatically_correct=True, recast=user_text)

        client = _get_client()
        if client is None:
            return EvaluationResult(corrections=[], is_grammatically_correct=True, recast=user_text)

        cefr = _DIFFICULTY_TO_CEFR.get(difficulty, "A1")
        concept_name = self._resolve_concept_name(concept)
        system_prompt = (
            f"{MARTA_PERSONA}\n\n"
            "You are evaluating a learner's Spanish sentence. Use the RECAST technique.\n"
            "Return STRICT JSON with keys: is_correct (bool), recast (string), corrections (array).\n"
            "Each correction must be a single word or tiny phrase (<=3 words) focusing on the exact mistake.\n"
            "Each correction must have original, corrected, explanation, concept_id."
        )
        user_prompt = (
            f"Learner level: {cefr}\n"
            f"Target concept: {concept_name}\n"
            f"Sentence: {user_text}\n"
            "Evaluate only grammar relevant to the target concept."
        )

        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2,
                max_tokens=400,
            )
            content = (response.choices[0].message.content or "").strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[-1]
                if content.endswith("```"):
                    content = content[:-3]
                content = content.strip()
            data = json.loads(content)
            corrections = [
                Correction(
                    original=c.get("original", ""),
                    corrected=c.get("corrected", ""),
                    explanation=c.get("explanation", ""),
                    concept_id=c.get("concept_id", concept),
                )
                for c in data.get("corrections", [])
                if c.get("original") and c.get("corrected")
            ]
            recast = str(data.get("recast", "")).strip() or user_text
            return EvaluationResult(
                corrections=_explode_corrections(corrections),
                is_grammatically_correct=bool(data.get("is_correct", True)),
                recast=recast,
            )
        except Exception:
            return EvaluationResult(corrections=[], is_grammatically_correct=True, recast=user_text)

    def generate_reply(
        self,
        messages: list[ConversationMessage],
        topic: str,
        concept: str,
        difficulty: int = 1,
    ) -> str:
        """Legacy single-turn reply using RECAST instructions."""
        if not ai_available():
            return self._fallback_reply(topic)

        client = _get_client()
        if client is None:
            return self._fallback_reply(topic)

        cefr = _DIFFICULTY_TO_CEFR.get(difficulty, "A1")
        concept_name = self._resolve_concept_name(concept)
        history_lines: list[str] = []
        for msg in messages[-6:]:
            speaker = "AI" if msg.role == "ai" else "Learner"
            history_lines.append(f"{speaker}: {msg.content}")
        history_text = "\n".join(history_lines) if history_lines else "AI: Hola, ¿cómo estás?"
        last_user = next((m for m in reversed(messages) if m.role == "user"), None)
        learner_text = last_user.content if last_user else ""

        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            f"{MARTA_PERSONA}\n\n"
                            "You are NOT a teacher. Use the RECAST technique to model correct Spanish.\n"
                            "Never mention the learner's mistakes explicitly. Keep the reply natural and encouraging.\n"
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Learner level: {cefr}\n"
                            f"Topic: {topic}\n"
                            f"Grammar target: {concept_name}\n"
                            f"Conversation so far:\n{history_text}\n\n"
                            f"Learner just said: {learner_text}\n"
                            "Respond in Spanish with 1-2 sentences."
                        ),
                    },
                ],
                temperature=0.7,
                max_tokens=250,
            )
            content = (response.choices[0].message.content or "").strip()
            return content if content else self._fallback_reply(topic)
        except Exception:
            return self._fallback_reply(topic)

    # ── Active methods ───────────────────────────────────────────────────

    @staticmethod
    def should_end(conversation: ConversationCard) -> bool:
        """Return True if user has sent max_turns messages."""
        return conversation.user_turn_count >= conversation.max_turns

    def generate_summary(
        self,
        conversation: ConversationCard,
        persona_prompt: str | None = None,
        persona_name: str = "Marta",
    ) -> ConversationSummary:
        """Post-conversation: list corrections, concepts practiced, score."""
        _ = persona_prompt
        conversation.persona_name = persona_name or conversation.persona_name
        all_corrections: list[Correction] = []
        concepts_practiced: set[str] = {conversation.concept}
        user_messages = 0
        correct_messages = 0

        for msg in conversation.messages:
            if msg.role == "user":
                user_messages += 1
                if msg.corrections:
                    all_corrections.extend(msg.corrections)
                    for c in msg.corrections:
                        concepts_practiced.add(c.concept_id)
                else:
                    correct_messages += 1

        score = correct_messages / user_messages if user_messages > 0 else 0.0

        return ConversationSummary(
            corrections=all_corrections,
            concepts_practiced=sorted(concepts_practiced),
            turn_count=conversation.turn_count,
            score=score,
        )

    # ── Internal helpers ─────────────────────────────────────────────────

    @staticmethod
    def _resolve_concept_name(concept_id: str) -> str:
        concepts = load_concepts()
        concept = concepts.get(concept_id)
        return concept.name if concept else concept_id

    @staticmethod
    def _get_concept_ids() -> list[str]:
        concepts = load_concepts()
        return list(concepts.keys())

    @staticmethod
    def _fallback_opener(topic: str, concept: str, difficulty: int) -> str:
        """Simple fallback opener when AI is unavailable."""
        openers_by_difficulty: dict[int, list[str]] = {
            1: [
                f"¡Hola! ¿Te gusta {topic}?",
                f"¡Hola! ¿Qué es {topic} para ti?",
                f"¡Oye! ¿Te interesa {topic}?",
                f"¡Hola! ¿Conoces algo de {topic}?",
                f"¡Hey! ¿Qué sabes de {topic}?",
                f"¡Hola! Hablemos de {topic}. ¿Qué opinas?",
                f"¡Hola! ¿{topic.capitalize()} es importante para ti?",
                f"¡Buenas! ¿Te gusta {topic}?",
            ],
            2: [
                f"¡Oye! ¿Qué piensas sobre {topic}?",
                f"¡Hola! ¿Cuál es tu experiencia con {topic}?",
                f"¡Hey! ¿Has tenido alguna experiencia con {topic}?",
                f"¡Buenas! ¿Qué opinas de {topic}?",
                f"¡Hola! Cuéntame algo sobre {topic}.",
                f"¿Sabías algo interesante sobre {topic}?",
                f"¡Oye! ¿Te gustaría hablar sobre {topic}?",
                f"¡Hola! ¿Qué te parece {topic}?",
            ],
            3: [
                f"¡Buenas! Me encanta hablar de {topic}. ¿Y a ti?",
                f"¡Hola! ¿Qué rol juega {topic} en tu vida?",
                f"¡Oye! ¿Cuál es tu opinión sobre {topic} hoy en día?",
                f"¡Hey! ¿Cómo ha cambiado {topic} en los últimos años?",
                f"¡Buenas! ¿Qué es lo más interesante de {topic} para ti?",
                f"¡Hola! Si pudieras cambiar algo de {topic}, ¿qué sería?",
                f"¡Oye! ¿Qué relación tienes con {topic}?",
                f"¡Buenas! ¿Cuál es tu aspecto favorito de {topic}?",
            ],
        }
        options = openers_by_difficulty.get(difficulty, openers_by_difficulty[1])
        return random.choice(options)

    @staticmethod
    def _fallback_reply(topic: str) -> str:
        replies = [
            f"¡Qué interesante! Cuéntame más sobre {topic}.",
            f"Bueno, eso es genial. ¿Qué más me puedes decir de {topic}?",
            f"¡Ah, sí! A mí también me interesa {topic}. ¿Y tú?",
            f"Pues, me encanta hablar de {topic}. ¿Qué opinas tú?",
        ]
        return random.choice(replies)

    @staticmethod
    def _fallback_respond(
        topic: str,
        user_text: str,
        messages: list[ConversationMessage],
    ) -> RespondResult:
        """Fallback when AI is unavailable."""
        replies = [
            f"¡Qué interesante! Cuéntame más sobre {topic}.",
            f"Bueno, eso es genial. ¿Qué más me puedes decir de {topic}?",
            f"¡Ah, sí! A mí también me interesa {topic}. ¿Y tú?",
            f"Pues, me encanta hablar de {topic}. ¿Qué opinas tú?",
        ]
        return RespondResult(
            ai_reply=random.choice(replies),
            corrections=[],
            is_grammatically_correct=True,
            should_continue=True,
            hint=None,
        )


__all__ = [
    "CONCEPT_STEERING",
    "ConversationCard",
    "ConversationEngine",
    "ConversationMessage",
    "ConversationSummary",
    "Correction",
    "EvaluationResult",
    "MARTA_PERSONA",
    "RespondResult",
    "SCAFFOLDING_RULES",
    "get_concept_steering",
    "get_random_topic",
]
