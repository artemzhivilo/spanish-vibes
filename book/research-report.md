# Research Report: Building an Adaptive Spanish Learning App

## Table of Contents

1. [CEFR Framework & A1/A2 Spanish Descriptors](#1-cefr-framework--a1a2-spanish-descriptors)
2. [Duolingo's Approach](#2-duolingos-approach)
3. [Second Language Acquisition (SLA) Research](#3-second-language-acquisition-sla-research)
4. [Item Response Theory (IRT) & Knowledge Tracing](#4-item-response-theory-irt--knowledge-tracing)
5. [Concept Graphs & Prerequisite Structures](#5-concept-graphs--prerequisite-structures)
6. [MCQ Distractor Design](#6-mcq-distractor-design)
7. [Practical Takeaways for Implementation](#7-practical-takeaways-for-implementation)

---

## 1. CEFR Framework & A1/A2 Spanish Descriptors

### What is CEFR?

The Common European Framework of Reference for Languages (CEFR) organizes language proficiency into six levels grouped into three bands:

| Band | Levels | Label |
|------|--------|-------|
| A | A1, A2 | Basic User |
| B | B1, B2 | Independent User |
| C | C1, C2 | Proficient User |

The framework defines competency through **can-do descriptors** -- statements describing what a learner can actually do at each level, rather than what grammar they know. The 2020 Companion Volume expanded these descriptors significantly, adding coverage for mediation, online interaction, and plurilingual competence.

### A1 Level -- Breakthrough / Beginner

**Communicative competence:**
- Understand and use familiar everyday expressions and very basic phrases
- Introduce oneself and others
- Ask and answer questions about personal details (where you live, people you know, things you have)
- Interact in a simple way provided the other person speaks slowly and clearly

**Grammar inventory (from Instituto Cervantes Plan Curricular):**
- Present tense of regular verbs (-ar, -er, -ir)
- Key irregular verbs: ser, estar, tener, ir, hacer, querer, poder
- Definite and indefinite articles (el/la/los/las, un/una/unos/unas)
- Gender and number agreement of nouns and adjectives
- Subject pronouns (yo, tu, el/ella, nosotros, etc.)
- Basic question words (que, donde, cuando, como, cuanto)
- Demonstratives (este, ese, aquel)
- Possessive adjectives (mi, tu, su)
- Hay (existential "there is/are")
- Basic negation (no)
- Very basic prepositions (en, de, a, con)

**Vocabulary topics:**
- Greetings and introductions
- Numbers, days of the week, months, time
- Family members
- Food and drink
- Colors, clothing
- Basic places and directions
- Classroom objects

**Approximate vocabulary size:** 500-700 words

### A2 Level -- Waystage / Elementary

**Communicative competence:**
- Understand sentences and frequently used expressions related to areas of immediate relevance (personal/family info, shopping, local geography, employment)
- Communicate in simple, routine tasks requiring direct exchange of information on familiar matters
- Describe aspects of background, immediate environment, and matters of immediate need
- Communicate about present, past, and future in simple terms

**Grammar additions beyond A1:**
- Preterite tense (preterito indefinido) for completed past actions
- Imperfect tense (preterito imperfecto) for descriptions and habitual past
- Basic future (ir + a + infinitive, and simple future)
- Direct and indirect object pronouns (me, te, lo/la, le)
- Reflexive verbs (levantarse, llamarse)
- Comparatives and superlatives (mas...que, menos...que, el mas...)
- More prepositions and prepositional phrases
- Adverbs of frequency (siempre, nunca, a veces)
- Basic connectors (y, pero, porque, cuando)
- Imperative mood (basic commands)

**Vocabulary topics:**
- Work and professions
- Daily routines
- Weather and seasons
- Health and body parts
- Hobbies and leisure
- Travel and transportation
- Shopping and money

**Approximate vocabulary size:** 1,200-1,500 words

### Key Structural Insight

The CEFR does NOT prescribe a specific order for teaching grammar within a level. The Instituto Cervantes Plan Curricular (https://cvc.cervantes.es/ensenanza/biblioteca_ele/plan_curricular/) provides the most authoritative inventory of which grammar, vocabulary, and functions belong at each level for Spanish specifically, but sequencing within a level is left to course designers.

**Practical takeaway:** The CEFR gives us a clear destination (what learners should be able to do) and a rough inventory of required knowledge, but the path through that inventory is ours to design.

---

## 2. Duolingo's Approach

### Course Structure

Duolingo's Spanish course is organized into:
- **Sections** (roughly 7-9, mapping to CEFR levels): Sections 1-3 cover A1-A2, Sections 4-6 cover B1-B2
- **Units** within sections (239 total for Spanish -- the largest of any Duolingo course)
- **Lessons** within units (typically 3-8 lessons per unit)
- **Exercises** within lessons (typically 10-20 per lesson)

Each unit focuses on a concept cluster (e.g., "Food," "Present Tense," "Family"), and Duolingo recently added CEFR-aligned quizzes at section boundaries.

### The Birdbrain Model

Duolingo's core ML system is called **Birdbrain**. Key technical details:

1. **Dual estimation:** Birdbrain simultaneously estimates (a) the difficulty of each exercise and (b) the current proficiency of each learner for each concept.

2. **Elo-like rating system:** The system is a generalization of the Elo rating system from chess. When a learner gets an exercise wrong, the system lowers the estimate of their ability and raises the estimate of the exercise's difficulty, and vice versa.

3. **Real-time updates:** Within minutes of completing an exercise, Birdbrain updates its model of the learner's knowledge state. It processes approximately 1.25 billion exercises per day.

4. **Student model:** Tracks statistics about every word ever taught to a learner, including frequency of exposure and recall accuracy.

5. **Personalized practice:** Uses the knowledge model to select exercises that best match the learner's current level -- targeting the zone where the learner has roughly a 75-80% chance of getting the answer correct (the "desirable difficulty" sweet spot).

### Half-Life Regression (HLR)

Duolingo's published spaced repetition model (Settles & Meeder, ACL 2016) replaces traditional SM-2 with a trainable model:

**Core formula:**

```
p = 2^(-delta/h)
```

Where:
- `p` = probability of correctly recalling an item
- `delta` = time elapsed since last practice (lag time)
- `h` = half-life of the item in the learner's memory

**Half-life estimation:**

```
h = 2^(theta dot x)
```

Where:
- `x` = feature vector for the student-word pair (includes number of times seen, number correct, number incorrect, time since last seen, etc.)
- `theta` = learned weight vector

**Key results:**
- 45%+ reduction in prediction error compared to baselines (Leitner, Pimsleur, SM-2)
- A/B testing showed: +9.5% retention for practice sessions, +1.7% for lessons, +12% for overall activity
- The model is trainable from data rather than relying on fixed schedules

**Practical takeaway:** HLR is elegant and implementable. The core insight is that the "half-life" of a memory depends on learnable features of both the student and the item. A simpler version could use just: (1) number of times practiced, (2) number of times correct, (3) time since last practice as features.

### Exercise Generation

- Duolingo's exercises are built from **human-authored sentence pairs** (not algorithmically generated)
- They now use LLMs to generate draft exercises faster, but human review remains essential
- Exercise types include: translation (L1->L2 and L2->L1), listening, speaking, matching, fill-in-the-blank, tap-the-word
- Distractors for MCQ-style exercises are generated from a combination of rules and ML models

### Concept Ordering

Duolingo's concept ordering is based on:
1. **Linguistic prerequisites** (you need nouns before noun-adjective agreement)
2. **Frequency** (high-frequency words and structures first)
3. **Communicative utility** (can the learner say something useful?)
4. **Error analysis** (Duolingo analyzed learner errors to identify curriculum pain points and reorganized accordingly)
5. **Spaced interleaving** (concepts are revisited at increasing intervals throughout the path)

Sources:
- [Duolingo Blog: How we learn how you learn](https://blog.duolingo.com/how-we-learn-how-you-learn/)
- [Duolingo Blog: Introducing Birdbrain](https://blog.duolingo.com/learning-how-to-help-you-learn-introducing-birdbrain/)
- [HLR Paper (PDF)](https://research.duolingo.com/papers/settles.acl16.pdf)
- [HLR GitHub](https://github.com/duolingo/halflife-regression)
- [IEEE Spectrum: How Duolingo's AI Learns](https://spectrum.ieee.org/duolingo)
- [Duolingo Research](https://research.duolingo.com/)

---

## 3. Second Language Acquisition (SLA) Research

### 3.1 Optimal Concept Ordering for Spanish

Research converges on several principles for ordering what to teach:

**High-frequency vocabulary first ("Super 7" verbs):**
The comprehensible input community, led by Terry Waltz, identified seven high-frequency Spanish verbs that should be taught first because they enable the widest range of expression:

1. **es** (is -- identity/description)
2. **tiene** (has -- possession)
3. **le gusta** (likes -- preference)
4. **hay** (there is/are -- existence)
5. **esta** (is -- location/state)
6. **va a** (is going to -- future/motion)
7. **quiere** (wants -- desire)

This expands to the "Sweet 16" by adding: puede (can), necesita (needs), sabe (knows), ve (sees), hace (does/makes), dice (says), pone (puts), da (gives), viene (comes).

**Natural order hypothesis (Krashen):**
Stephen Krashen's research suggests that grammatical structures are acquired in a predictable order regardless of instruction. For Spanish:
- Present tense before past tense
- Regular forms before irregular forms
- Indicative before subjunctive
- Simple sentences before complex/embedded clauses

**Communicative utility principle:**
Structures that let learners accomplish real tasks should come before structures that are grammatically "simpler" but less useful. For example, "Quiero..." (I want...) + infinitive is more immediately useful than learning to conjugate all present tense regular verbs.

**Recommended A1 sequence:**
1. Greetings, basic courtesy phrases
2. Super 7 verbs (in yo/el-ella forms first)
3. Nouns with articles (gender/number)
4. Basic adjective agreement
5. Numbers, time, dates
6. Present tense regular verbs (-ar first, then -er/-ir)
7. Common irregular present tense verbs
8. Basic questions (interrogatives)
9. Negation
10. Basic prepositions (en, de, a, con)

### 3.2 Error Analysis / Interlanguage Theory

**Interlanguage** (Selinker, 1972) refers to the evolving linguistic system a learner constructs between L1 and L2. It is systematic, rule-governed, and reveals predictable patterns.

**Common errors English speakers make in Spanish:**

| Error Type | Example | Root Cause |
|-----------|---------|------------|
| Ser/Estar confusion | *"Soy cansado"* (should be "estoy") | English has one "to be" verb |
| Gender agreement | *"La problema"* (should be "el problema") | English lacks grammatical gender |
| Adjective placement | *"Rojo coche"* (should be "coche rojo") | English puts adjectives before nouns |
| False cognates | *"Estoy embarazado"* (means pregnant, not embarrassed) | L1 transfer |
| Por/Para confusion | *"Es por ti"* vs *"Es para ti"* | Both translate to "for" in English |
| Preterite/Imperfect | *"Yo fui al cine cada sabado"* (should be "iba") | English uses one past tense for both |
| Subject pronoun overuse | *"Yo quiero, yo tengo, yo soy..."* | English requires subject pronouns; Spanish is pro-drop |
| Preposition transfer | *"Pensar sobre"* (should be "pensar en") | Direct translation of English prepositions |
| Subjunctive avoidance | *"Quiero que tu vienes"* (should be "vengas") | English has vestigial subjunctive |
| Reflexive verb omission | *"Me llamo"* omitted as *"Llamo Juan"* | English reflexives are rare |

**Error classification framework:**
- **Interlingual errors**: Caused by L1 (English) interference (ser/estar, adjective placement)
- **Intralingual errors**: Caused by overgeneralization of L2 rules (regularizing irregular verbs: *"yo sabo"* instead of "yo se")
- **Developmental errors**: Part of natural acquisition order (these are expected and temporary)

### 3.3 Diagnostic Testing with Wrong Answers

The key principle from diagnostic language assessment research:

> "A good diagnostic question should be about a specific concept and each incorrect answer should reveal a different misconception. It should not be possible for a student to correctly answer using an existing misconception."

**Three components of Diagnostic Language Assessment (DLA):**
1. **Identification of specific weaknesses** (not just "wrong" but "why wrong")
2. **Review of relevant materials** targeting those specific weaknesses
3. **Re-assessment** to verify the misconception has been resolved

**Cognitive Diagnostic Models (CDMs)** can be applied to language learning to extract fine-grained information about which specific knowledge components a learner has mastered, using patterns of correct and incorrect responses.

### 3.4 Knowledge Component Models for Language

Knowledge Components (KCs) are defined by Koedinger et al. as "an acquired unit of cognitive function or structure that can be inferred from performance on a set of related tasks."

**For Spanish, KCs can be decomposed along multiple dimensions:**

**Grammar KCs (examples):**
- `present_tense_ar_regular` -- Can conjugate regular -ar verbs in present tense
- `ser_vs_estar_permanent` -- Knows to use ser for permanent characteristics
- `ser_vs_estar_location` -- Knows to use estar for location
- `gender_agreement_noun` -- Can assign correct gender to nouns
- `gender_agreement_adj` -- Can make adjectives agree with noun gender
- `preterite_regular_ar` -- Can form regular -ar preterite
- `preterite_vs_imperfect_completed` -- Uses preterite for completed actions

**Vocabulary KCs:**
- `vocab_recognition_[word]` -- Can recognize meaning L2->L1
- `vocab_production_[word]` -- Can produce L2 from L1
- `vocab_spelling_[word]` -- Can spell the L2 word correctly

**Pragmatic/Functional KCs:**
- `can_greet_formally` -- Knows formal greeting conventions
- `can_order_food` -- Can perform a restaurant ordering task
- `can_describe_person` -- Can describe physical appearance

**Key granularity insight:** KCs should be small enough to be individually testable but large enough to be meaningful. A single exercise often tests multiple KCs simultaneously (e.g., a sentence translation might test verb conjugation + gender agreement + word order).

Sources:
- [Krashen: Principles and Practice in SLA](https://www.sdkrashen.com/content/books/principles_and_practice.pdf)
- [CARLA: Overview of Error Analysis](https://archive.carla.umn.edu/learnerlanguage/error_analysis.html)
- [CARLA: Interlanguage](https://archive.carla.umn.edu/learnerlanguage/interlanguage.html)
- [Super 7 Verbs](https://comprehensibleclassroom.com/2014/05/08/super7sweet16)
- [KLI Framework (Koedinger et al.)](https://pact.cs.cmu.edu/pubs/PSLC-Theory-Framework-Tech-Rep.pdf)

---

## 4. Item Response Theory (IRT) & Knowledge Tracing

### 4.1 Item Response Theory (IRT)

IRT models the probability that a learner with ability `theta` will correctly answer an item with certain parameters. Three main models:

**1PL (Rasch) Model:**
```
P(correct) = 1 / (1 + e^(-(theta - b)))
```
- `theta` = learner ability
- `b` = item difficulty
- Simple but powerful; items characterized by difficulty only

**2PL Model:**
```
P(correct) = 1 / (1 + e^(-a(theta - b)))
```
- Adds `a` = item discrimination (how well the item differentiates high/low ability learners)

**3PL Model:**
```
P(correct) = c + (1-c) / (1 + e^(-a(theta - b)))
```
- Adds `c` = guessing parameter (probability of correct answer by pure guessing)
- Most appropriate for MCQs where guessing is a factor

**Key property of IRT:** Item parameters are *sample-independent* -- once calibrated on pilot data, they work for any learner population. This enables Computer Adaptive Testing (CAT), where items of known difficulty are selected in real-time based on the learner's estimated ability.

### 4.2 Bayesian Knowledge Tracing (BKT)

BKT models learning as a Hidden Markov Model with a binary latent state: the learner either "knows" or "does not know" a particular knowledge component.

**Four parameters:**

| Parameter | Symbol | Meaning |
|-----------|--------|---------|
| Prior knowledge | P(L0) | Probability the learner already knew the skill before any practice |
| Learn rate | P(T) | Probability the learner transitions from "not known" to "known" on each practice opportunity |
| Guess rate | P(G) | Probability of a correct answer despite not knowing the skill |
| Slip rate | P(S) | Probability of an incorrect answer despite knowing the skill |

**Update equations:**

After observing a correct response:
```
P(L_t | correct) = P(L_t) * (1 - P(S)) / [P(L_t) * (1 - P(S)) + (1 - P(L_t)) * P(G)]
```

After observing an incorrect response:
```
P(L_t | incorrect) = P(L_t) * P(S) / [P(L_t) * P(S) + (1 - P(L_t)) * (1 - P(G))]
```

Learning transition:
```
P(L_{t+1}) = P(L_t | obs) + (1 - P(L_t | obs)) * P(T)
```

**Constraint:** P(G) + P(S) < 1 (otherwise the model degenerates)

**Mastery threshold:** A learner is typically considered to have "mastered" a KC when P(L_t) > 0.95.

### 4.3 Comparison: BKT vs IRT vs Simple Hit-Rate

| Feature | Simple Hit-Rate | IRT | BKT |
|---------|----------------|-----|-----|
| **What it models** | % correct overall | Ability at a point in time | Knowledge state over time |
| **Learning over time** | No (static) | No (static) | Yes (transition model) |
| **Guessing/slipping** | No | Yes (3PL) | Yes (explicit parameters) |
| **Item difficulty** | No | Yes (core feature) | Indirect only |
| **Complexity** | Trivial | Moderate | Moderate |
| **Data requirements** | Minimal | Moderate (needs calibrated items) | Moderate |
| **Best for** | Quick dashboards | Placement tests, adaptive item selection | Mastery tracking during learning |
| **Interpretability** | High | High | High |
| **Updatable** | Per-answer | Requires recalculation | Per-answer (Bayesian update) |

### 4.4 Practical Recommendation

For an adaptive Spanish learning app, a **hybrid approach** works best:

1. **Use BKT (or simplified BKT) for knowledge tracing** -- Track mastery of each knowledge component over time. This tells you *what the learner knows right now*.

2. **Use HLR-style decay for spaced repetition** -- Model forgetting with a half-life that depends on practice history. This tells you *when to review*.

3. **Use IRT-like item difficulty for exercise selection** -- Target exercises where the learner has roughly 75-80% chance of success (the "zone of proximal development").

A simplified practical model could be:
- Track `(n_correct, n_attempts, last_seen_timestamp)` per knowledge component per learner
- Estimate mastery as a smoothed success rate with a Bayesian prior (essentially simplified BKT)
- Estimate recall probability using HLR: `p = 2^(-time_since_last / half_life)` where half_life grows with successful reviews
- Schedule review when `p` drops below a threshold (e.g., 0.8)

Sources:
- [IRT Wikipedia](https://en.wikipedia.org/wiki/Item_response_theory)
- [BKT Wikipedia](https://en.wikipedia.org/wiki/Bayesian_knowledge_tracing)
- [pyBKT Introduction](https://www.mdpi.com/2624-8611/5/3/50)
- [Deep Knowledge Tracing (Stanford)](https://stanford.edu/~cpiech/bio/papers/deepKnowledgeTracing.pdf)
- [Settles & Meeder HLR Paper](https://research.duolingo.com/papers/settles.acl16.pdf)

---

## 5. Concept Graphs & Prerequisite Structures

### What is a Concept Prerequisite Graph?

A concept prerequisite graph (or Educational Knowledge Graph) is a directed acyclic graph (DAG) where:
- **Nodes** represent knowledge components / concepts
- **Directed edges** represent prerequisite relationships (A -> B means "A must be learned before B")

### Prerequisite Types in Language Learning

**Hard prerequisites (must-know-first):**
- You cannot learn adjective-noun agreement without knowing nouns and adjectives
- You cannot learn preterite vs. imperfect without knowing both tenses
- You cannot learn object pronouns without knowing verb conjugation

**Soft prerequisites (helpful-to-know-first):**
- Knowing food vocabulary makes restaurant scenarios more accessible
- Knowing numbers helps with time/date lessons
- Knowing present tense makes past tense explanations clearer by contrast

**Co-requisites (learn together):**
- Noun gender and articles are deeply linked
- Ser and estar benefit from contrastive teaching
- Regular verb paradigms across -ar/-er/-ir can be taught in close succession

### Example Concept Graph for A1 Spanish

```
greetings
    |
    v
subject_pronouns --> present_tense_regular_ar
    |                        |
    v                        v
nouns_gender --> articles --> adjective_agreement
    |                        |
    v                        v
numbers --> time_dates    ser_vs_estar_basics
    |                        |
    v                        v
question_words           present_tense_irregular
    |                        |
    v                        v
prepositions_basic       ir_a_infinitive (near future)
    |                        |
    v                        v
basic_conversation       negation
```

### Research Findings on Knowledge Graph Structure

Key findings from the educational data mining literature:

1. **DAG structure is essential** -- Cycles in prerequisite graphs create impossible learning paths. The graph must be acyclic.

2. **Shallow is better than deep** -- Very long prerequisite chains (A->B->C->D->E->F) frustrate learners because they must master many things before reaching their goal. Prefer wider, shallower graphs.

3. **Multiple paths increase flexibility** -- Having multiple ways to reach a concept allows personalization. If a learner struggles with path A->C, they might succeed via path B->C.

4. **Prerequisite relationships can be mined from data** -- Systems can automatically discover prerequisites by analyzing which concepts learners typically master before others. If learners who haven't mastered A consistently fail at B, A is likely a prerequisite for B.

5. **Knowledge graph embeddings enable recommendation** -- Node embeddings from the graph can be used for concept recommendation, prerequisite prediction, and learning path generation.

### Practical Implementation

For a Spanish learning app, the concept graph should:
- Be manually curated initially (based on linguistic knowledge)
- Be refined with data (track which failures correlate with missing prerequisites)
- Support multiple learning paths (not a single linear sequence)
- Be used to: (a) unlock new concepts when prerequisites are mastered, (b) recommend review of prerequisites when a learner struggles

Sources:
- [ACE: AI-Assisted Construction of Educational Knowledge Graphs](https://jedm.educationaldatamining.org/index.php/JEDM/article/view/737)
- [Exploring Knowledge Graphs for Concept Prerequisites](https://slejournal.springeropen.com/articles/10.1186/s40561-019-0104-3)
- [Knowledge Graphs in Education Survey](https://www.sciencedirect.com/science/article/pii/S2405844024014142)

---

## 6. MCQ Distractor Design

### What Makes a Good Distractor?

A distractor is a wrong answer option in a multiple-choice question. Research identifies several qualities of effective distractors:

**Diagnostic distractors** reveal specific misconceptions. Each wrong answer maps to a different error type:

```
Question: "She is tired" -> _____ cansada.

A) Esta     <-- CORRECT
B) Es       <-- Reveals: ser/estar confusion (permanent vs temporary)
C) Tiene    <-- Reveals: L1 transfer ("she has tired" pattern from French/Italian)
D) Hay      <-- Reveals: fundamental verb confusion (too easy to eliminate = bad distractor)
```

Option D is a poor distractor because it is too obviously wrong. Options B and C are excellent because selecting them tells you exactly what the learner misunderstands.

### Principles for Distractor Design

1. **Each distractor should correspond to exactly one misconception.** If a learner selects it, you know precisely what they got wrong.

2. **Distractors should be plausible.** They should be the same part of speech, similar in form, and the kind of error a real learner would make. Use actual student error data when possible.

3. **Distractors should be homogeneous in form.** All options should look similar (same length, same grammatical category, same format).

4. **Avoid "none of the above" and "all of the above."** These don't diagnose anything.

5. **Semantic similarity matters.** The best distractors are semantically close to the correct answer but wrong in a specific, identifiable way.

6. **Use actual student errors as distractors.** Research shows that distractors based on real errors outperform those designed by experts guessing at what errors might occur. Extracting common wrong answers from open-response data is the gold standard.

### Distractor Categories for Spanish MCQs

| Category | Distractor Strategy | What It Diagnoses |
|----------|-------------------|-------------------|
| **Gender confusion** | Wrong article/adjective gender | Gender assignment / agreement rules |
| **Verb form confusion** | Wrong conjugation of correct verb | Conjugation paradigm errors |
| **Tense confusion** | Correct verb, wrong tense | Tense selection rules |
| **Ser/Estar swap** | Other copula verb | Copula selection rules |
| **False cognate** | Cognate that doesn't mean what student thinks | L1 interference |
| **Preposition swap** | Wrong preposition | Preposition selection (por/para, etc.) |
| **Word order error** | Same words, wrong order | L2 syntax rules |
| **Overgeneralization** | Regularized irregular form | Irregular morphology knowledge |

### Automatic Distractor Generation

Recent research on automatic distractor generation uses:
- **Semantic similarity models** to find words close in meaning but wrong in context
- **Collocation patterns** to find words that appear in similar contexts
- **Morphological variation** to generate wrong verb forms
- **WordNet/embedding-based** approaches to find semantically related but incorrect alternatives
- **LLMs** to generate plausible distractors, though research shows they still struggle to capture real student misconceptions without human review

**Key finding:** LLMs can generate grammatically plausible distractors but significantly underperform human-designed distractors at capturing *actual* common student errors. The best approach is to seed distractors from real student error data and supplement with algorithmically generated options.

Sources:
- [Automatic Distractor Generation: Systematic Review (PMC)](https://pmc.ncbi.nlm.nih.gov/articles/PMC11623049/)
- [Distractor Generation Survey](https://arxiv.org/html/2402.01512v2)
- [Generating Competitive Distractors from Student Error Data](https://zenodo.org/records/15870234)
- [Automatic Distractor Generation for Vocabulary Questions](https://telrp.springeropen.com/articles/10.1186/s41039-018-0082-z)

---

## 7. Practical Takeaways for Implementation

### Architecture Recommendations

**1. Knowledge Component Model**

Define your KC inventory along two axes:
- **Grammar KCs** (~50-80 for A1-A2): Each is a specific, testable grammatical skill
- **Vocabulary KCs** (~1,000-1,500 for A1-A2): Each word has recognition and production sub-skills

Structure these in a prerequisite DAG. Keep the graph shallow (max depth 5-6) and allow multiple paths.

**2. Learner Model (Simplified BKT + HLR Hybrid)**

For each (learner, KC) pair, track:
```python
class KCState:
    n_attempts: int       # total practice opportunities
    n_correct: int        # total correct responses
    last_seen: datetime   # timestamp of last practice
    half_life: float      # estimated memory half-life (hours)
    p_mastery: float      # estimated probability of mastery (0-1)
```

Update rules:
- After each response, update `p_mastery` using simplified Bayesian update
- After correct response, increase `half_life` by a factor (e.g., 2x)
- After incorrect response, decrease `half_life` by a factor (e.g., 0.5x)
- Estimate current recall: `p_recall = 2^(-hours_since_last / half_life)`
- Schedule review when `p_recall < 0.8`
- Consider KC "mastered" when `p_mastery > 0.90` AND `n_attempts >= 5`

**3. Exercise Selection Algorithm**

Priority ordering for what to practice next:
1. **Due for review:** KCs where `p_recall` has dropped below threshold (spaced repetition)
2. **In progress:** KCs that are unlocked but not yet mastered (active learning)
3. **New concepts:** KCs whose prerequisites are all mastered (progression)

Within each category, prefer exercises targeting the learner's weakest KCs.

**4. Diagnostic MCQ Design**

For each KC, design MCQs where:
- The correct answer tests the target KC
- Each distractor maps to a specific misconception
- Track which distractors are selected to build a misconception profile
- Use the misconception profile to prioritize remedial content

Example data structure:
```python
class MCQOption:
    text: str
    is_correct: bool
    misconception_tag: str | None  # e.g., "ser_estar_confusion", "gender_error"
    target_kc: str | None          # KC that this misconception relates to
```

**5. Concept Ordering for A1 Spanish**

Based on the research, a recommended unit sequence:

| Order | Unit | Key Grammar KCs | Key Vocab |
|-------|------|-----------------|-----------|
| 1 | Greetings & Basics | greeting phrases, courtesy | hola, gracias, por favor |
| 2 | Identity | ser + yo/tu/el, subject pronouns | name, nationality, profession |
| 3 | Descriptions | ser + adjectives, gender agreement | adjectives, colors |
| 4 | Things | nouns, articles, gender, hay | common objects, food |
| 5 | Possession | tener, possessive adjectives | family, numbers |
| 6 | Preferences | gustar construction | hobbies, food preferences |
| 7 | Location | estar + location, prepositions | places, directions |
| 8 | Actions | present tense -ar verbs | daily activities |
| 9 | More Actions | present tense -er/-ir verbs | more activities |
| 10 | Daily Life | reflexive verbs, time | routine, schedule |
| 11 | Wants & Plans | querer, ir a + infinitive | plans, desires |
| 12 | Questions | interrogatives, word order | question words |
| 13 | Past Events | preterite (regular) | time expressions |
| 14 | Descriptions (Past) | imperfect (intro) | childhood, memories |
| 15 | Commands | basic imperative | instructions |

**6. Implementation Priorities**

Based on research, the highest-impact features to build first:

1. **Spaced repetition with forgetting model** -- Even a simple version (SM-2 or basic HLR) dramatically improves retention
2. **Knowledge component tracking** -- Know what each learner has mastered vs. not
3. **Diagnostic distractors** -- Make wrong answers informative, not random
4. **Prerequisite-gated progression** -- Don't let learners advance past unmastered prerequisites
5. **Desirable difficulty targeting** -- Select exercises at ~75-80% expected success rate

Features that can wait:
- Full IRT item calibration (requires large user base)
- Deep Knowledge Tracing (requires massive data, marginal gains over BKT)
- Automatic distractor generation (start with hand-crafted, data-mine later)

---

## Key Sources & Further Reading

### CEFR
- [Council of Europe: CEFR Level Descriptions](https://www.coe.int/en/web/common-european-framework-reference-languages/level-descriptions)
- [CEFR Companion Volume 2020](https://rm.coe.int/cefr-companion-volume-with-new-descriptors-2018/1680787989)
- [Instituto Cervantes Plan Curricular A1-A2 Grammar](https://cvc.cervantes.es/ensenanza/biblioteca_ele/plan_curricular/niveles/02_gramatica_inventario_a1-a2.htm)
- [Kwiziq: CEFR for Spanish](https://spanish.kwiziq.com/test/what-is-cefr-common-european-framework-of-reference-for-languages)

### Duolingo Research
- [Half-Life Regression Paper (ACL 2016)](https://research.duolingo.com/papers/settles.acl16.pdf)
- [Half-Life Regression GitHub](https://github.com/duolingo/halflife-regression)
- [Duolingo Research Portal](https://research.duolingo.com/)
- [Machine Learning-Driven Language Assessment (TACL 2020)](https://research.duolingo.com/papers/settles.tacl20.pdf)
- [Duolingo Blog: How we learn how you learn](https://blog.duolingo.com/how-we-learn-how-you-learn/)
- [Duolingo Blog: Introducing Birdbrain](https://blog.duolingo.com/learning-how-to-help-you-learn-introducing-birdbrain/)
- [IEEE Spectrum: How Duolingo's AI Learns](https://spectrum.ieee.org/duolingo)

### SLA & Error Analysis
- [Krashen: Principles and Practice in SLA](https://www.sdkrashen.com/content/books/principles_and_practice.pdf)
- [CARLA: Error Analysis](https://archive.carla.umn.edu/learnerlanguage/error_analysis.html)
- [CARLA: Interlanguage](https://archive.carla.umn.edu/learnerlanguage/interlanguage.html)
- [Super 7 & Sweet 16 Verbs](https://comprehensibleclassroom.com/2014/05/08/super7sweet16)

### Knowledge Tracing & IRT
- [BKT Wikipedia](https://en.wikipedia.org/wiki/Bayesian_knowledge_tracing)
- [IRT Wikipedia](https://en.wikipedia.org/wiki/Item_response_theory)
- [pyBKT Paper](https://www.mdpi.com/2624-8611/5/3/50)
- [Deep Knowledge Tracing (Stanford)](https://stanford.edu/~cpiech/bio/papers/deepKnowledgeTracing.pdf)
- [KLI Framework (Koedinger et al.)](https://pact.cs.cmu.edu/pubs/PSLC-Theory-Framework-Tech-Rep.pdf)

### Concept Prerequisites
- [ACE: AI-Assisted Educational Knowledge Graphs](https://jedm.educationaldatamining.org/index.php/JEDM/article/view/737)
- [Exploring Knowledge Graphs for Prerequisites](https://slejournal.springeropen.com/articles/10.1186/s40561-019-0104-3)

### MCQ & Distractor Design
- [Automatic Distractor Generation: Systematic Review](https://pmc.ncbi.nlm.nih.gov/articles/PMC11623049/)
- [Distractor Generation Survey (2024)](https://arxiv.org/html/2402.01512v2)
- [Generating Competitive Distractors from Error Data](https://zenodo.org/records/15870234)
