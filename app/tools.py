"""Tool definitions for the Claude agent.

Each tool is a dict matching the Anthropic tool-use schema.

TUTOR_TOOLS — full set, used by the Tutor persona for structured teaching.
CHAT_TOOLS  — minimal set, used by conversation personas (no teaching tools).
TOOLS       — alias for TUTOR_TOOLS (backward compat).
"""

TOOLS = [
    {
        "name": "create_fill_in_blank",
        "description": (
            "Drop a tiny inline fill-in-the-blank exercise into the chat. Use "
            "sparingly — at most once per few exchanges, only when something "
            "the learner just said makes a contextual exercise feel natural. "
            "Each item should test one missing word from a short Spanish "
            "sentence, ideally tied to what was just discussed."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "intro": {
                    "type": "string",
                    "description": "One sentence in your voice (Spanish), introducing the exercise.",
                },
                "sentences": {
                    "type": "array",
                    "minItems": 2,
                    "maxItems": 4,
                    "items": {
                        "type": "object",
                        "properties": {
                            "text_with_blank": {
                                "type": "string",
                                "description": "Spanish sentence with a single ___ where the missing word goes.",
                            },
                            "answer": {
                                "type": "string",
                                "description": "The single correct word.",
                            },
                            "hint": {
                                "type": "string",
                                "description": "Optional short English hint.",
                            },
                        },
                        "required": ["text_with_blank", "answer"],
                    },
                },
            },
            "required": ["intro", "sentences"],
        },
    },
    {
        "name": "create_multiple_choice",
        "description": (
            "Drop a multiple-choice question into the chat. Great for testing "
            "vocabulary, grammar, or comprehension. One question per call."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "intro": {
                    "type": "string",
                    "description": "One sentence in your voice (Spanish) setting up the question.",
                },
                "question": {
                    "type": "string",
                    "description": "The question (Spanish or English depending on what you're testing).",
                },
                "options": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 4,
                    "maxItems": 4,
                    "description": "Four answer options. Exactly one must be correct.",
                },
                "correct_index": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 3,
                    "description": "Index (0-3) of the correct option.",
                },
                "explanation": {
                    "type": "string",
                    "description": "Brief explanation shown after the learner answers.",
                },
            },
            "required": [
                "intro",
                "question",
                "options",
                "correct_index",
                "explanation",
            ],
        },
    },
    {
        "name": "create_flashcard_set",
        "description": (
            "Show a set of 3-6 vocabulary flashcards inline. Spanish on front, "
            "English on back. Use to introduce new words or review vocabulary."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "intro": {
                    "type": "string",
                    "description": "One sentence intro in your voice (Spanish).",
                },
                "cards": {
                    "type": "array",
                    "minItems": 3,
                    "maxItems": 6,
                    "items": {
                        "type": "object",
                        "properties": {
                            "front": {
                                "type": "string",
                                "description": "Spanish word or short phrase.",
                            },
                            "back": {
                                "type": "string",
                                "description": "English translation.",
                            },
                            "example": {
                                "type": "string",
                                "description": "Optional example sentence in Spanish.",
                            },
                        },
                        "required": ["front", "back"],
                    },
                },
            },
            "required": ["intro", "cards"],
        },
    },
    {
        "name": "create_grammar_note",
        "description": (
            "Show a concise grammar explanation card inline. Use when the "
            "learner keeps making the same mistake or asks about a rule."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Grammar topic, e.g. 'Ser vs Estar'.",
                },
                "explanation": {
                    "type": "string",
                    "description": "Plain-language explanation in English. 1-3 sentences.",
                },
                "examples": {
                    "type": "array",
                    "minItems": 2,
                    "maxItems": 4,
                    "items": {
                        "type": "object",
                        "properties": {
                            "spanish": {"type": "string"},
                            "english": {"type": "string"},
                        },
                        "required": ["spanish", "english"],
                    },
                },
            },
            "required": ["title", "explanation", "examples"],
        },
    },
    {
        "name": "create_quiz_set",
        "description": (
            "Drop a rapid-fire drill set of 5-8 multiple-choice questions. "
            "Duolingo-style: the learner powers through them one by one, "
            "wrong answers come back at the end for a retry."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "intro": {
                    "type": "string",
                    "description": "One sentence in your voice (Spanish) introducing the drill.",
                },
                "topic": {
                    "type": "string",
                    "description": "Short label for the topic.",
                },
                "questions": {
                    "type": "array",
                    "minItems": 5,
                    "maxItems": 8,
                    "items": {
                        "type": "object",
                        "properties": {
                            "question": {"type": "string"},
                            "options": {
                                "type": "array",
                                "items": {"type": "string"},
                                "minItems": 4,
                                "maxItems": 4,
                            },
                            "correct_index": {
                                "type": "integer",
                                "minimum": 0,
                                "maximum": 3,
                            },
                        },
                        "required": ["question", "options", "correct_index"],
                    },
                },
            },
            "required": ["intro", "topic", "questions"],
        },
    },
    {
        "name": "run_placement_test",
        "description": (
            "Run an adaptive placement test to assess the learner's CEFR level. "
            "Use at the start of a first session or when the learner asks to check their level."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "Brief explanation of why you're running the test.",
                },
            },
            "required": ["reason"],
        },
    },
    {
        "name": "save_learner_notes",
        "description": (
            "Save your full markdown notes about this learner to disk. Call "
            "at the end of a session. Include everything worth keeping."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "notes": {
                    "type": "string",
                    "description": "Full markdown body. Overwrites the file.",
                },
            },
            "required": ["notes"],
        },
    },
]

# Tutor gets all tools — structured teaching, quizzes, vocab, grammar, placement
TUTOR_TOOLS = TOOLS

# Chat personas get only save_learner_notes — no teaching tools
CHAT_TOOLS = [t for t in TOOLS if t["name"] == "save_learner_notes"]
