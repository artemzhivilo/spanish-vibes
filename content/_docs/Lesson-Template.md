---
chapter_slug: chXX-topic
lesson_slug: chXX-YY-short-slug
title: Human-friendly lesson title
order_index: 1
summary: "1–3 lines explaining the lesson focus"
tags: [tag1, tag2]
decks: [vocab, verbs, fillblank, exercises]
status: draft
---

<!-- Replace placeholders with lesson-specific content. Keep markdown tidy and consistent. -->

```concept
id: conj-template
kind: conjugation_pattern
title: Placeholder -ar pattern
summary: Brief description of the verb group or pattern.
pattern: Describe the ending changes or stem rules.
scope: When/where this pattern applies.
examples:
  - "yo canto"
  - "nosotros cantamos"
variants:
  - note: "Mention stem shifts or spelling notes if any"
practice.generate:
  seeds:
    - "cantar"
    - "bailar"
  persons: [1s,2s,3s,1p,2p,3p]
```

```concept
id: irregular-template
kind: irregular_group
title: Placeholder irregular verbs
summary: Explain what links these verbs.
rule: Highlight their shared irregularity.
examples:
  - "yo voy"
  - "ellos van"
practice.generate:
  seeds:
    - "ir"
    - "tener"
  persons: [1s,2s,3s]
```

```concept
id: stemchange-template
kind: stem_change_pattern
title: Placeholder stem change (e → ie)
summary: Describe the stem vowel shift.
pattern: Root vowel change + endings.
examples:
  - "yo pienso"
  - "ellos piensan"
practice.generate:
  seeds:
    - "pensar"
    - "querer"
  persons: [1s,3s,3p]
```

```concept
id: connector-template
kind: grammar_connector_rule
title: Placeholder connector usage
summary: Explain how the connector works.
rule: Outline placement and punctuation.
examples:
  - "Estudio y practico."
  - "Quiero ir, pero llueve."
practice.generate:
  seeds:
    - "y"
    - "pero"
  persons: [1s,2s,3s]
```

```concept
id: syntax-template
kind: syntax_rule
title: Placeholder sentence order
summary: Explain the base word order.
rule: Subject + Verb + Complement for neutral statements.
examples:
  - "Ella prepara café."
  - "Nosotros vivimos en Lima."
counterexamples:
  - "Prepara ella café." (mark why it sounds marked)
practice.generate:
  seeds:
    - "cocinar"
    - "visitar"
  persons: [1s,3s]
```

```concept
id: agreement-template
kind: agreement_rule
title: Placeholder agreement rule
summary: Describe gender/number matching.
rule: Adjectives match the noun they describe.
examples:
  - "la casa blanca"
  - "los chicos altos"
practice.generate:
  seeds:
    - "blanco"
    - "alto"
  persons: [3p]
```

```concept
id: pronoun-template
kind: pronoun_usage
title: Placeholder direct objects
summary: When to use lo/la/los/las.
rule: Pronoun precedes conjugated verb.
examples:
  - "Lo veo."
  - "Las compramos."
practice.generate:
  seeds:
    - "lo"
    - "las"
  persons: [1s,1p]
```

```concept
id: preposition-template
kind: preposition_rule
title: Placeholder prepositions a/de/en
summary: Clarify core uses and contractions.
rule: Use "a" for direction, "de" for origin, "en" for location.
constraints:
  - "Use al/del contractions with el"
examples:
  - "Voy a la tienda."
  - "Vengo del parque."
practice.generate:
  seeds:
    - "a"
    - "de"
    - "en"
  persons: [1s,2s,3s]
```

```concept
id: question-template
kind: question_rule
title: Placeholder question words
summary: Introduce interrogatives with accents.
rule: Inversion after question words.
examples:
  - "¿Dónde vives?"
  - "¿Cómo estás?"
practice.generate:
  seeds:
    - "dónde"
    - "cómo"
  persons: [2s]
```

```concept
id: negation-template
kind: negation_rule
title: Placeholder basic negation
summary: Use "no" before the verb.
rule: Single "no" precedes conjugated verb.
examples:
  - "No como carne."
  - "No vivimos lejos."
practice.generate:
  seeds:
    - "no"
  persons: [1s,1p]
```

```concept
id: article-template
kind: article_rule
title: Placeholder definite vs indefinite
summary: When to pick el/la/los/las vs un/una/unos/unas.
rule: Definite for known items; indefinite for new/general.
examples:
  - "El perro duerme."
  - "Una amiga llama."
practice.generate:
  seeds:
    - "el"
    - "una"
  persons: [3s]
```

```concept
id: periphrasis-template
kind: periphrasis_rule
title: Placeholder tener que + infinitive
summary: Express obligation with tener que.
pattern: Tener conjugated + que + infinitive.
examples:
  - "Tengo que estudiar."
  - "Tenemos que irnos."
practice.generate:
  seeds:
    - "tener que estudiar"
    - "tener que trabajar"
  persons: [1s,1p]
```

```concept
id: gustar-template
kind: gustar_rule
title: Placeholder gustar usage
summary: Clarify indirect object pronouns with gustar.
rule: Me/te/le + gusta(n) + subject.
examples:
  - "Me gusta la música."
  - "Les gustan los libros."
practice.generate:
  seeds:
    - "gustar"
  persons: [3s,3p]
```

## Vocabulary
spanish | english | example
---|---|---
placeholder | placeholder | "Write a short example sentence."

## Fill in the blank
Escribe aquí una oración con {{gap}}.
Añade otra frase con {{gap}}.

## Exercises
```exercise
type: mcq
prompt: Replace with lesson-specific question.
options:
  - "option A"
  - "option B"
answer: "option A"
feedback:
  correct: "Short encouragement."
  incorrect: "Hint for retry."
```

```exercise
type: typein
prompt: "Translate: __"
answer: "target answer"
case_sensitive: false
```
