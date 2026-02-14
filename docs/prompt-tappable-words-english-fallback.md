# Prompt: Tappable Word Translation + English Fallback Detection

Feed this to Claude Code after the conversation engine v2 prompt.

---

## Context

In the spanish-vibes FastAPI + HTMX app, conversation cards show AI messages
in Spanish. Two problems:

1. Users can't understand AI messages if they don't know certain words,
   which kills the conversation dead
2. When users type English because they don't know the Spanish word, the
   app treats it as broken Spanish instead of recognizing it as a
   vocabulary gap signal

## Change 1: Tappable word translations on AI messages

Every Spanish word in AI conversation messages should be tappable to show
an English translation.

### Backend: Word translation endpoint

Create a new lightweight endpoint in flow_routes.py:

```python
@router.get("/flow/translate-word", response_class=HTMLResponse)
async def translate_word(
    request: Request,
    word: str = Query(...),
    context: str = Query(""),  # surrounding sentence for disambiguation
) -> Response:
    """Return a tooltip with the English translation of a Spanish word."""
```

Implementation options (in order of preference):

1. **Local dictionary first (fastest, free):** Bundle a Spanish-English
   dictionary as a JSON file or SQLite table. There are free CC-licensed
   Spanish-English dictionaries available. Look up the word (lemmatized
   if possible — "comiste" → "comer" → "to eat"). For the prototype,
   even a 5000-word dictionary covers 95% of A1-A2 vocabulary.

2. **LLM fallback for unknown words:** If the word isn't in the local
   dictionary, make a quick gpt-4o-mini call:
   "Translate the Spanish word '{word}' to English. Context: '{context}'.
   Return ONLY the English translation, 1-3 words max."

3. **Cache translations aggressively:** Store every translation in a
   `word_translations` table (spanish_word, english_translation, context,
   created_at). Never look up the same word twice.

### Frontend: Wrappable words in conversation template

In templates/partials/flow_conversation.html, update how AI messages render.

Create a Jinja2 filter or template helper that wraps each word in the AI
message with a tappable span:

```python
# In flow_routes.py or a template helpers file
def make_words_tappable(text: str) -> str:
    """Wrap each word in a span that can trigger translation on tap."""
    import re
    words = re.split(r'(\s+|[¡¿.,!?;:])', text)
    result = []
    for part in words:
        if re.match(r'[a-záéíóúñü]+', part, re.IGNORECASE):
            # It's a word — make it tappable
            escaped = part.replace('"', '&quot;')
            result.append(
                f'<span class="tappable-word cursor-pointer hover:bg-violet-500/20 '
                f'hover:rounded px-0.5 transition-colors" '
                f'data-word="{escaped}">{part}</span>'
            )
        else:
            result.append(part)
    return ''.join(result)
```

Register this as a Jinja2 filter in the templates setup:

```python
templates.env.filters["tappable"] = make_words_tappable
```

Then in the template, change AI message rendering from:
```html
{{ msg.content }}
```
to:
```html
{{ msg.content | tappable | safe }}
```

### Frontend: Translation tooltip (JS)

Add a small script to flow_conversation.html that handles word taps:

```html
<script>
(function() {
  // Translation tooltip element (create once, reuse)
  var tooltip = document.createElement('div');
  tooltip.id = 'word-tooltip';
  tooltip.className = 'fixed z-50 bg-slate-800 text-emerald-300 text-sm ' +
    'px-3 py-2 rounded-lg shadow-xl ring-1 ring-slate-700 ' +
    'pointer-events-none opacity-0 transition-opacity duration-150';
  tooltip.style.maxWidth = '200px';
  document.body.appendChild(tooltip);

  // Dismiss on tap elsewhere
  document.addEventListener('click', function(e) {
    if (!e.target.classList.contains('tappable-word')) {
      tooltip.style.opacity = '0';
    }
  });

  // Handle word taps
  document.addEventListener('click', function(e) {
    if (!e.target.classList.contains('tappable-word')) return;

    var word = e.target.dataset.word;
    // Get surrounding sentence for context
    var parent = e.target.closest('.rounded-2xl');
    var context = parent ? parent.textContent.trim().substring(0, 100) : '';

    // Position tooltip near the tapped word
    var rect = e.target.getBoundingClientRect();
    tooltip.style.left = rect.left + 'px';
    tooltip.style.top = (rect.bottom + 6) + 'px';
    tooltip.textContent = '...';
    tooltip.style.opacity = '1';

    // Fetch translation
    fetch('/flow/translate-word?word=' + encodeURIComponent(word) +
          '&context=' + encodeURIComponent(context))
      .then(function(r) { return r.text(); })
      .then(function(html) {
        tooltip.innerHTML = html;
      })
      .catch(function() {
        tooltip.textContent = '(translation unavailable)';
      });
  });
})();
</script>
```

The endpoint should return a small HTML snippet:

```html
<div>
  <span class="font-bold text-emerald-300">{{ word }}</span>
  <span class="text-slate-400 mx-1">→</span>
  <span class="text-slate-200">{{ translation }}</span>
</div>
```

### Mobile-friendly: tooltip positioning

The tooltip should handle edge cases:
- If the word is near the bottom of the screen, show tooltip ABOVE
- If the word is near the right edge, shift tooltip left
- Add a small caret/arrow pointing to the word
- Dismiss on scroll or second tap

## Change 2: English fallback detection

When a user types English (or mixed English/Spanish) in a conversation,
the app should:

1. Detect that it's English
2. Translate it to Spanish
3. Show the user what they should have said
4. Continue the conversation as if they said it in Spanish
5. Track the vocabulary gap for future practice

### Language detection in conversation engine

In conversation.py, add a method to the ConversationEngine:

```python
def detect_and_handle_english(
    self, user_text: str, concept: str, difficulty: int
) -> EnglishFallbackResult | None:
    """Detect if user typed English and translate to Spanish.
    Returns None if the text is Spanish."""
```

The EnglishFallbackResult dataclass:

```python
@dataclass(slots=True)
class EnglishFallbackResult:
    original_english: str
    spanish_translation: str
    vocabulary_gaps: list[VocabularyGap]  # words they didn't know
    display_message: str  # friendly message to show user

@dataclass(slots=True)
class VocabularyGap:
    english_word: str
    spanish_word: str
    concept_id: str | None  # map to concept if possible
```

### Detection approach

For language detection, DON'T use a heavy library. Use a simple heuristic:

```python
# Common Spanish words that confirm it's Spanish
_SPANISH_MARKERS = {
    'el', 'la', 'los', 'las', 'un', 'una', 'de', 'en', 'que', 'es',
    'yo', 'tú', 'él', 'ella', 'nosotros', 'muy', 'pero', 'como',
    'por', 'para', 'con', 'sin', 'más', 'también', 'ser', 'estar',
    'hoy', 'ayer', 'mañana', 'sí', 'no', 'bien', 'mal', 'aquí',
}

# Common English words that confirm it's English
_ENGLISH_MARKERS = {
    'the', 'is', 'are', 'was', 'were', 'have', 'has', 'had',
    'do', 'does', 'did', 'will', 'would', 'could', 'should',
    'i', 'you', 'he', 'she', 'we', 'they', 'my', 'your',
    'this', 'that', 'these', 'those', 'with', 'from', 'about',
}

def _detect_language(text: str) -> str:
    """Simple heuristic: 'es', 'en', or 'mixed'."""
    words = set(text.lower().split())
    es_count = len(words & _SPANISH_MARKERS)
    en_count = len(words & _ENGLISH_MARKERS)

    if en_count > es_count and en_count >= 2:
        return "en"
    if es_count > en_count:
        return "es"
    if en_count >= 1 and es_count >= 1:
        return "mixed"
    return "es"  # default to Spanish
```

### When English is detected

If the user types English or mixed, use a single LLM call:

```
The learner typed this in English during a Spanish conversation:
"{user_text}"

1. Translate their message to natural Spanish at {cefr} level.
2. Identify which specific English words/phrases they didn't know in
   Spanish (these are vocabulary gaps to practice later).
3. Generate a brief encouraging message.

Return JSON:
{
  "spanish_translation": "...",
  "vocabulary_gaps": [
    {"english": "store", "spanish": "tienda"},
    {"english": "yesterday", "spanish": "ayer"}
  ],
  "encouragement": "¡Buena idea! En español sería..."
}
```

### Show the translation to the user in the conversation

When English is detected, instead of just passing the English text to
Marta, show an intermediate message in the conversation:

```
[User bubble - blue]: "I went to the store yesterday"

[System bubble - violet, smaller text]:
  "💡 En español: 'Ayer fui a la tienda'"
  "📝 New vocabulary: store → tienda, yesterday → ayer"

[Then Marta continues the conversation as if they said it in Spanish]
```

In the template, add a new bubble style for system translation messages:

```html
<!-- System translation bubble -->
<div class="flex items-start gap-2 max-w-[90%] mx-auto">
  <div class="rounded-xl bg-violet-500/10 px-4 py-2.5 text-sm
              text-violet-300 leading-relaxed ring-1 ring-violet-500/20">
    <p class="font-medium">💡 En español: <span class="text-emerald-300">{{ spanish_translation }}</span></p>
    {% if vocabulary_gaps %}
    <p class="text-xs text-slate-400 mt-1">
      📝 New:
      {% for gap in vocabulary_gaps %}
        <span class="text-violet-400">{{ gap.english }}</span>
        <span class="text-slate-600">→</span>
        <span class="text-emerald-400">{{ gap.spanish }}</span>
        {% if not loop.last %} · {% endif %}
      {% endfor %}
    </p>
    {% endif %}
  </div>
</div>
```

### Track vocabulary gaps for future practice

The vocabulary gaps should feed back into the learning system:

1. Store gaps in a new `vocabulary_gaps` table:
   ```sql
   CREATE TABLE IF NOT EXISTS vocabulary_gaps (
       id INTEGER PRIMARY KEY AUTOINCREMENT,
       english_word TEXT NOT NULL,
       spanish_word TEXT NOT NULL,
       concept_id TEXT,
       source TEXT DEFAULT 'conversation',  -- where it was discovered
       times_seen INTEGER DEFAULT 0,
       times_correct INTEGER DEFAULT 0,
       created_at TEXT NOT NULL
   );
   ```

2. When generating future MCQs, prioritize vocabulary the user has
   explicitly shown they don't know (from this table).

3. After N conversation cards, occasionally serve a "vocabulary review"
   card that specifically tests recently discovered gaps.

### Update the flow in flow_routes.py

In the `conversation_respond` route, add English detection BEFORE
calling respond_to_user:

```python
# Check for English fallback
english_result = engine.detect_and_handle_english(
    user_message.strip(), concept_id, difficulty
)

if english_result:
    # Store vocabulary gaps
    for gap in english_result.vocabulary_gaps:
        store_vocabulary_gap(gap.english_word, gap.spanish_word, gap.concept_id)

    # Add the user's English message to conversation
    user_msg = ConversationMessage(
        role="user", content=user_message.strip(), timestamp=timestamp
    )
    messages.append(user_msg)

    # Add system translation message
    system_msg = ConversationMessage(
        role="system",
        content=english_result.display_message,
        timestamp=timestamp,
    )
    # Store the translation info for the template
    # (add english_result to template context)

    # Use the Spanish translation as input to Marta
    result = engine.respond_to_user(
        messages=messages,
        user_text=english_result.spanish_translation,  # Marta sees Spanish
        topic=topic,
        concept=concept_id,
        difficulty=difficulty,
    )
else:
    # Normal Spanish input flow
    result = engine.respond_to_user(...)
```

## Change 3: Bundle a basic Spanish-English dictionary

Create data/es_en_dictionary.json with the top 3000-5000 most common
Spanish words and their English translations. Structure:

```json
{
  "hola": "hello",
  "adiós": "goodbye",
  "comer": "to eat",
  "comí": "I ate (comer, preterite)",
  "comiste": "you ate (comer, preterite)",
  ...
}
```

For the MVP, you can generate this with an LLM call:
"Generate a JSON dictionary of the 3000 most common Spanish words
with English translations. For conjugated verbs, include the infinitive
and tense in parentheses. Format: {"spanish": "english"}"

Or use a free dictionary source. The key is having SOMETHING local
so 95% of word lookups don't need an API call.

## Testing

1. Test tappable word rendering: verify make_words_tappable wraps words
   correctly and preserves punctuation and whitespace
2. Test language detection: "I went to the store" → "en",
   "Fui a la tienda" → "es", "I fui to the tienda" → "mixed"
3. Test English fallback: verify it returns Spanish translation +
   vocabulary gaps
4. Test vocabulary gap storage: verify gaps are saved to DB
5. Test dictionary lookup: verify local dictionary returns translations
   for common words and falls back to LLM for unknown ones
