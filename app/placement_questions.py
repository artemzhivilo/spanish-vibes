"""Placement test question bank.

~50 questions tagged by CEFR level for adaptive placement testing.
Each question has: question text, 4 options, correct_index, level tag,
grammar_topic tag.

Level numeric mapping:
  0 = A1, 1 = A1-A2, 2 = A2, 3 = A2-B1, 4 = B1, 5 = B1-B2
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PlacementQuestion:
    question: str
    options: list[str]
    correct_index: int
    level: float  # 0=A1, 1=A1-A2, 2=A2, 3=A2-B1, 4=B1, 5=B1-B2
    level_label: str  # e.g. "A1", "A2-B1"
    grammar_topic: str


QUESTION_BANK: list[PlacementQuestion] = [
    # ---- A1 (level 0) ----
    PlacementQuestion(
        question='What does "hola" mean?',
        options=["Goodbye", "Hello", "Please", "Thank you"],
        correct_index=1,
        level=0,
        level_label="A1",
        grammar_topic="greetings",
    ),
    PlacementQuestion(
        question="Yo ___ estudiante.",
        options=["soy", "estoy", "tengo", "hago"],
        correct_index=0,
        level=0,
        level_label="A1",
        grammar_topic="ser present",
    ),
    PlacementQuestion(
        question='What does "gato" mean?',
        options=["Dog", "Cat", "Bird", "Fish"],
        correct_index=1,
        level=0,
        level_label="A1",
        grammar_topic="basic vocabulary",
    ),
    PlacementQuestion(
        question="Ella ___ una hermana.",
        options=["tiene", "es", "hace", "va"],
        correct_index=0,
        level=0,
        level_label="A1",
        grammar_topic="tener present",
    ),
    PlacementQuestion(
        question="El libro es ___.",
        options=["roja", "rojo", "rojos", "rojas"],
        correct_index=1,
        level=0,
        level_label="A1",
        grammar_topic="adjective agreement",
    ),
    PlacementQuestion(
        question="___ llamas?",
        options=["Cómo te", "Qué te", "Dónde te", "Cuándo te"],
        correct_index=0,
        level=0,
        level_label="A1",
        grammar_topic="question words",
    ),
    PlacementQuestion(
        question="Nosotros ___ en una casa grande.",
        options=["vivemos", "vivimos", "viven", "vives"],
        correct_index=1,
        level=0,
        level_label="A1",
        grammar_topic="regular -ir present",
    ),
    PlacementQuestion(
        question="Me ___ el chocolate.",
        options=["gusto", "gustan", "gusta", "gustas"],
        correct_index=2,
        level=0,
        level_label="A1",
        grammar_topic="gustar",
    ),
    # ---- A1-A2 (level 1) ----
    PlacementQuestion(
        question="Ella ___ levanta a las siete.",
        options=["se", "le", "me", "te"],
        correct_index=0,
        level=1,
        level_label="A1-A2",
        grammar_topic="reflexive verbs",
    ),
    PlacementQuestion(
        question="Nosotros ___ a ir al cine.",
        options=["voy", "va", "vamos", "van"],
        correct_index=2,
        level=1,
        level_label="A1-A2",
        grammar_topic="ir a + infinitive",
    ),
    PlacementQuestion(
        question="Yo no ___ nada.",
        options=["sé", "soy", "tengo", "hago"],
        correct_index=0,
        level=1,
        level_label="A1-A2",
        grammar_topic="saber present",
    ),
    PlacementQuestion(
        question="Ellos ___ jugando al fútbol.",
        options=["son", "están", "tienen", "hacen"],
        correct_index=1,
        level=1,
        level_label="A1-A2",
        grammar_topic="estar + gerund",
    ),
    PlacementQuestion(
        question="Mi madre ___ la comida todos los días.",
        options=["cocina", "cocine", "cocinó", "cocinaba"],
        correct_index=0,
        level=1,
        level_label="A1-A2",
        grammar_topic="present tense habitual",
    ),
    PlacementQuestion(
        question="Yo quiero ___ un café.",
        options=["tomo", "tomar", "tomando", "tomé"],
        correct_index=1,
        level=1,
        level_label="A1-A2",
        grammar_topic="verb + infinitive",
    ),
    PlacementQuestion(
        question='What does "cansado" mean?',
        options=["Happy", "Tired", "Hungry", "Angry"],
        correct_index=1,
        level=1,
        level_label="A1-A2",
        grammar_topic="vocabulary adjectives",
    ),
    # ---- A2 (level 2) ----
    PlacementQuestion(
        question="Ayer yo ___ al supermercado.",
        options=["fui", "iba", "voy", "ir"],
        correct_index=0,
        level=2,
        level_label="A2",
        grammar_topic="preterite irregular ir",
    ),
    PlacementQuestion(
        question="El año pasado ellos ___ en Madrid.",
        options=["vivían", "vivieron", "viven", "vivir"],
        correct_index=1,
        level=2,
        level_label="A2",
        grammar_topic="preterite regular -ir",
    ),
    PlacementQuestion(
        question="Cuando era niño, ___ mucho al parque.",
        options=["fui", "iba", "voy", "iré"],
        correct_index=1,
        level=2,
        level_label="A2",
        grammar_topic="imperfect habitual",
    ),
    PlacementQuestion(
        question="El libro ___ compré ayer es muy bueno.",
        options=["que", "cual", "quien", "donde"],
        correct_index=0,
        level=2,
        level_label="A2",
        grammar_topic="relative pronoun que",
    ),
    PlacementQuestion(
        question="Este regalo es ___ ti.",
        options=["por", "para", "de", "a"],
        correct_index=1,
        level=2,
        level_label="A2",
        grammar_topic="por vs para",
    ),
    PlacementQuestion(
        question="Ella es más alta ___ su hermano.",
        options=["que", "de", "como", "tan"],
        correct_index=0,
        level=2,
        level_label="A2",
        grammar_topic="comparatives",
    ),
    PlacementQuestion(
        question="Ya he ___ la tarea.",
        options=["terminando", "terminado", "terminar", "terminé"],
        correct_index=1,
        level=2,
        level_label="A2",
        grammar_topic="present perfect",
    ),
    PlacementQuestion(
        question="Gracias ___ tu ayuda.",
        options=["para", "por", "de", "a"],
        correct_index=1,
        level=2,
        level_label="A2",
        grammar_topic="por vs para",
    ),
    # ---- A2-B1 (level 3) ----
    PlacementQuestion(
        question="Ayer ___ lloviendo cuando ___ de casa.",
        options=[
            "estaba / salí",
            "estuvo / salía",
            "estaba / salía",
            "estuvo / salí",
        ],
        correct_index=0,
        level=3,
        level_label="A2-B1",
        grammar_topic="preterite vs imperfect",
    ),
    PlacementQuestion(
        question="Si tengo tiempo, ___ a visitarte.",
        options=["iré", "iría", "fui", "iba"],
        correct_index=0,
        level=3,
        level_label="A2-B1",
        grammar_topic="conditional vs future",
    ),
    PlacementQuestion(
        question="___ de llegar del trabajo.",
        options=["Acaba", "Acabo", "Acabé", "Acababa"],
        correct_index=1,
        level=3,
        level_label="A2-B1",
        grammar_topic="acabar de + infinitive",
    ),
    PlacementQuestion(
        question="Se lo ___ ayer.",
        options=["dije", "digo", "decía", "diré"],
        correct_index=0,
        level=3,
        level_label="A2-B1",
        grammar_topic="combined pronouns",
    ),
    PlacementQuestion(
        question="Mientras yo ___, mi hermano ___ la tele.",
        options=[
            "estudiaba / veía",
            "estudié / vio",
            "estudiaba / vio",
            "estudié / veía",
        ],
        correct_index=0,
        level=3,
        level_label="A2-B1",
        grammar_topic="preterite vs imperfect",
    ),
    PlacementQuestion(
        question="Trabajé allí ___ tres años.",
        options=["durante", "para", "desde", "hasta"],
        correct_index=0,
        level=3,
        level_label="A2-B1",
        grammar_topic="time expressions",
    ),
    PlacementQuestion(
        question="Me gustaría ___ a España este verano.",
        options=["viajo", "viajar", "viajando", "viajé"],
        correct_index=1,
        level=3,
        level_label="A2-B1",
        grammar_topic="conditional + infinitive",
    ),
    PlacementQuestion(
        question="No conozco a ___ que hable japonés.",
        options=["alguien", "nadie", "algo", "nada"],
        correct_index=1,
        level=3,
        level_label="A2-B1",
        grammar_topic="negative pronouns",
    ),
    # ---- B1 (level 4) ----
    PlacementQuestion(
        question="Espero que ___ buen tiempo mañana.",
        options=["hace", "haga", "hará", "hacía"],
        correct_index=1,
        level=4,
        level_label="B1",
        grammar_topic="subjunctive after esperar",
    ),
    PlacementQuestion(
        question="No creo que él ___ razón.",
        options=["tiene", "tenga", "tendrá", "tuviera"],
        correct_index=1,
        level=4,
        level_label="B1",
        grammar_topic="subjunctive after doubt",
    ),
    PlacementQuestion(
        question="Cuando ___ a casa, te llamaré.",
        options=["llego", "llegue", "llegaré", "llegué"],
        correct_index=1,
        level=4,
        level_label="B1",
        grammar_topic="subjunctive in temporal clauses",
    ),
    PlacementQuestion(
        question="Te lo digo para que lo ___.",
        options=["sabes", "sepas", "sabrás", "sabías"],
        correct_index=1,
        level=4,
        level_label="B1",
        grammar_topic="subjunctive after para que",
    ),
    PlacementQuestion(
        question="Me alegra que ___ aquí.",
        options=["estás", "estés", "estarás", "estabas"],
        correct_index=1,
        level=4,
        level_label="B1",
        grammar_topic="subjunctive after emotion",
    ),
    PlacementQuestion(
        question="Dijo que ___ al médico al día siguiente.",
        options=["iba", "va", "fue", "iría"],
        correct_index=3,
        level=4,
        level_label="B1",
        grammar_topic="reported speech",
    ),
    PlacementQuestion(
        question="Había ___ la puerta antes de que llegaran.",
        options=["cerrando", "cerrado", "cerrar", "cierra"],
        correct_index=1,
        level=4,
        level_label="B1",
        grammar_topic="past perfect",
    ),
    PlacementQuestion(
        question="En esta tienda se ___ ropa de segunda mano.",
        options=["vende", "venden", "vendió", "vendía"],
        correct_index=0,
        level=4,
        level_label="B1",
        grammar_topic="impersonal se",
    ),
    # ---- B1-B2 (level 5) ----
    PlacementQuestion(
        question="Si ___ más dinero, viajaría por todo el mundo.",
        options=["tengo", "tuviera", "tendría", "he tenido"],
        correct_index=1,
        level=5,
        level_label="B1-B2",
        grammar_topic="imperfect subjunctive conditional",
    ),
    PlacementQuestion(
        question="Aunque ___ lloviendo, salimos a pasear.",
        options=["está", "esté", "estaba", "estuviera"],
        correct_index=3,
        level=5,
        level_label="B1-B2",
        grammar_topic="subjunctive in concessive clauses",
    ),
    PlacementQuestion(
        question="Si hubiera sabido, no ___ eso.",
        options=[
            "habría dicho",
            "había dicho",
            "hubiera dicho",
            "habría dicho / hubiera dicho",
        ],
        correct_index=0,
        level=5,
        level_label="B1-B2",
        grammar_topic="past perfect subjunctive + conditional",
    ),
    PlacementQuestion(
        question="La película, ___ director es español, ganó un premio.",
        options=["que", "cual", "cuyo", "quien"],
        correct_index=2,
        level=5,
        level_label="B1-B2",
        grammar_topic="relative pronoun cuyo",
    ),
    PlacementQuestion(
        question="No es que no ___, es que no tengo tiempo.",
        options=["quiero", "quiera", "querría", "quisiera"],
        correct_index=1,
        level=5,
        level_label="B1-B2",
        grammar_topic="subjunctive after no es que",
    ),
    PlacementQuestion(
        question="Dado que ___ tarde, decidimos quedarnos en casa.",
        options=["era", "fuera", "sea", "fue"],
        correct_index=0,
        level=5,
        level_label="B1-B2",
        grammar_topic="advanced connectors",
    ),
    PlacementQuestion(
        question="Le pedí que me ___ la verdad.",
        options=["dice", "dijera", "diría", "dijo"],
        correct_index=1,
        level=5,
        level_label="B1-B2",
        grammar_topic="imperfect subjunctive after pedir",
    ),
    PlacementQuestion(
        question="El problema fue resuelto ___ los ingenieros.",
        options=["de", "por", "para", "con"],
        correct_index=1,
        level=5,
        level_label="B1-B2",
        grammar_topic="passive voice",
    ),
    PlacementQuestion(
        question="Ojalá ___ ir contigo, pero tengo que trabajar.",
        options=["puedo", "pudiera", "podría", "pueda"],
        correct_index=1,
        level=5,
        level_label="B1-B2",
        grammar_topic="ojalá + imperfect subjunctive",
    ),
]

# Numeric level -> CEFR label
LEVEL_MAP = {
    0: "A1",
    1: "A1",  # 0-1 rounds to A1
    2: "A2",  # 1-2 rounds to A2
    3: "B1",  # 2-3 rounds to B1
    4: "B1",
    5: "B2",  # 4-5 rounds to B2
}


def level_to_cefr(numeric: float) -> str:
    """Map a numeric difficulty level to a CEFR label."""
    if numeric < 1.0:
        return "A1"
    elif numeric < 2.0:
        return "A2"
    elif numeric < 3.5:
        return "B1"
    else:
        return "B2"
