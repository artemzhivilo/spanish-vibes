# PROMPT: Text-to-Speech & Voice Input

## What we're adding

Two voice features using the browser's native Web Speech API (free, no API keys, no backend changes):

1. **TTS (Text-to-Speech)** — A 🔊 button on persona messages, word cards, and MCQ questions that reads Spanish aloud. Essential for a language learning app.
2. **STT (Speech-to-Text)** — A 🎤 button in conversation mode that lets the user speak instead of type. The transcript fills the input field.

## Important constraints

- **User activation required** — `speechSynthesis.speak()` only works after a user click. Cannot auto-play.
- **Browser support** — Chrome/Edge: full support. Safari: mostly works. Firefox: TTS only, no STT. Always provide fallbacks.
- **No backend changes needed** — All voice features are pure client-side JavaScript.
- **Spanish voice selection** — Use `lang='es-ES'` and try to find a native Spanish voice from `speechSynthesis.getVoices()`.
- **Slow rate for learning** — Default TTS rate should be 0.85 (slightly slower than normal) for comprehension.

## Change 1: Add global speech utilities to flow.html

In `templates/flow.html`, add a `<script>` block (inside the existing script area or at the bottom of `<body>`) with the shared TTS/STT utility functions. These will be available to all card types and the conversation template.

```javascript
// ── Speech utilities ──────────────────────────────────────────
(function() {
  // TTS: Speak Spanish text
  window.speakSpanish = function(text, rate) {
    if (!window.speechSynthesis) return;
    speechSynthesis.cancel();

    var utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = 'es-ES';
    utterance.rate = rate || 0.85;
    utterance.pitch = 1;

    // Try to use a Spanish voice
    var voices = speechSynthesis.getVoices();
    var spanishVoice = voices.find(function(v) { return v.lang && v.lang.startsWith('es'); });
    if (spanishVoice) {
      utterance.voice = spanishVoice;
    }

    // Visual feedback: find the button that triggered this and animate it
    utterance.onstart = function() {
      var btn = document.querySelector('.speak-active');
      if (btn) btn.classList.add('animate-pulse');
    };
    utterance.onend = function() {
      var btn = document.querySelector('.speak-active');
      if (btn) btn.classList.remove('animate-pulse', 'speak-active');
    };

    speechSynthesis.speak(utterance);
  };

  // Preload voices (Chrome loads them async)
  if (window.speechSynthesis) {
    speechSynthesis.getVoices();
    speechSynthesis.onvoiceschanged = function() {
      speechSynthesis.getVoices();
    };
  }

  // STT: Start listening for Spanish speech, fill a target input
  window.startSpanishListening = function(inputSelector, statusSelector, micBtnSelector) {
    var SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      alert('Speech recognition is not supported in your browser. Please use Chrome or Edge.');
      return;
    }

    var recognition = new SpeechRecognition();
    recognition.lang = 'es-ES';
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.maxAlternatives = 1;

    var input = document.querySelector(inputSelector);
    var status = document.querySelector(statusSelector);
    var micBtn = document.querySelector(micBtnSelector);

    if (micBtn) {
      micBtn.classList.add('text-red-400', 'animate-pulse');
      micBtn.disabled = true;
    }
    if (status) {
      status.textContent = 'Escuchando...';
      status.classList.remove('hidden');
    }

    recognition.onresult = function(event) {
      var transcript = '';
      for (var i = event.resultIndex; i < event.results.length; i++) {
        transcript = event.results[i][0].transcript;
      }
      if (input) input.value = transcript;
    };

    recognition.onerror = function(event) {
      console.warn('Speech recognition error:', event.error);
      if (status) {
        if (event.error === 'no-speech') {
          status.textContent = 'No speech detected. Try again.';
        } else if (event.error === 'not-allowed') {
          status.textContent = 'Microphone access denied.';
        } else {
          status.textContent = 'Error: ' + event.error;
        }
      }
    };

    recognition.onend = function() {
      if (micBtn) {
        micBtn.classList.remove('text-red-400', 'animate-pulse');
        micBtn.disabled = false;
      }
      if (status) {
        setTimeout(function() { status.classList.add('hidden'); }, 2000);
      }
    };

    recognition.start();
  };
})();
```

## Change 2: TTS on word_intro cards

In `templates/partials/flow_card.html`, in the `word_intro` block (around line 56-76), add a speak button next to the Spanish word:

Find the word display section:
```html
<h2 class="text-3xl font-black text-slate-50">{{ card_context.word_spanish }}</h2>
```

Add a speak button right after it:
```html
<h2 class="text-3xl font-black text-slate-50">{{ card_context.word_spanish }}</h2>
<button type="button"
  onclick="this.classList.add('speak-active'); speakSpanish('{{ card_context.word_spanish }}')"
  class="mt-2 inline-flex items-center gap-1 rounded-full bg-violet-500/15 px-3 py-1 text-sm text-violet-300 transition hover:bg-violet-500/25"
  title="Listen to pronunciation">
  🔊 Listen
</button>
```

Also add a speak button for the example sentence if it exists:
```html
{% if card_context.word_sentence %}
  <p class="text-sm text-slate-400 mt-4">
    {{ card_context.word_sentence }}
    <button type="button"
      onclick="this.classList.add('speak-active'); speakSpanish('{{ card_context.word_sentence | replace("'", "\\'") }}')"
      class="inline ml-1 text-violet-400 hover:text-violet-300"
      title="Listen to example">🔊</button>
  </p>
{% endif %}
```

## Change 3: TTS on word_practice and fill_blank cards

For word_practice, add a speak button next to the sentence (the `word_sentence` field). In the word_practice block, find:
```html
<p class="mt-3 text-2xl font-bold text-slate-50 leading-snug">{{ card_context.word_sentence }}</p>
```

Add a speak button after it. Use the same pattern:
```html
<p class="mt-3 text-2xl font-bold text-slate-50 leading-snug">
  {{ card_context.word_sentence }}
  <button type="button"
    onclick="this.classList.add('speak-active'); speakSpanish('{{ card_context.word_sentence | replace("'", "\\'") }}')"
    class="inline ml-1 text-slate-400 hover:text-emerald-300 text-lg"
    title="Listen">🔊</button>
</p>
```

Do the same for the fill_blank card type — the sentence is displayed in `card_context.word_sentence`.

## Change 4: TTS on MCQ questions

For the MCQ card (the `{% else %}` default block), add a speak button after the question text. Find:
```html
<p class="text-2xl font-bold text-slate-50 leading-snug">{{ card_context.question }}</p>
```

Add:
```html
<p class="text-2xl font-bold text-slate-50 leading-snug">
  {{ card_context.question }}
  <button type="button"
    onclick="this.classList.add('speak-active'); speakSpanish('{{ card_context.question | replace("'", "\\'") }}')"
    class="inline ml-1 text-slate-400 hover:text-emerald-300 text-lg"
    title="Listen">🔊</button>
</p>
```

## Change 5: TTS on conversation AI messages

In `templates/partials/flow_conversation.html`, add a speak button inside each AI message bubble. Find where AI messages are rendered (the `data-chat-role="ai"` block). The message content is in a div with the text.

After the message text content, add a small speak button:

```html
<div class="rounded-2xl rounded-tl-sm bg-slate-700 px-4 py-2.5 text-sm text-slate-200 leading-relaxed">
  {{ msg.content | tappable | safe }}
  <button type="button"
    onclick="this.classList.add('speak-active'); speakSpanish(this.parentElement.textContent.replace('🔊', '').trim())"
    class="inline ml-1 text-slate-400 hover:text-violet-300 text-xs opacity-60 hover:opacity-100 transition"
    title="Listen">🔊</button>
</div>
```

Note: We use `this.parentElement.textContent` to grab the raw text (stripping any HTML from the tappable filter), then trim out the speaker emoji itself.

## Change 6: STT (voice input) in conversation mode

In `templates/partials/flow_conversation.html`, add a microphone button to the input form. Find the input form area with the text input and send button.

Add a mic button between the text input and the send button:

```html
<div class="flex items-center gap-2">
  <input type="text" name="user_message"
    id="conv-user-input"
    placeholder="Escribe en español..."
    autocomplete="off" autofocus
    class="..." />

  <button type="button"
    id="conv-mic-btn"
    onclick="startSpanishListening('#conv-user-input', '#conv-mic-status', '#conv-mic-btn')"
    class="shrink-0 rounded-xl bg-[#0f1a1f] p-3 text-xl text-slate-400 transition hover:text-violet-300 hover:bg-violet-500/10"
    title="Speak in Spanish">
    🎤
  </button>

  <button type="submit" class="...">Send</button>
</div>

<p id="conv-mic-status" class="hidden text-xs text-violet-300 mt-1 text-center"></p>
```

The mic button calls `startSpanishListening()` which:
1. Starts the browser's speech recognition in Spanish
2. Shows "Escuchando..." status
3. Fills the text input with the transcript as the user speaks
4. The user can then review and hit Send (or edit the transcript first)

**Important:** STT is NOT auto-submit. The user sees their transcribed text and presses Send. This lets them fix recognition errors before submitting.

## Change 7: Feature detection & graceful degradation

In the global script (Change 1), add feature detection that hides buttons when APIs aren't available:

```javascript
// After DOM loads, hide unsupported features
document.addEventListener('DOMContentLoaded', function() {
  // Hide TTS buttons if not supported
  if (!window.speechSynthesis) {
    document.querySelectorAll('[title="Listen"], [title="Listen to pronunciation"], [title="Listen to example"]').forEach(function(btn) {
      btn.style.display = 'none';
    });
  }

  // Hide STT buttons if not supported
  if (!window.SpeechRecognition && !window.webkitSpeechRecognition) {
    document.querySelectorAll('#conv-mic-btn, [title="Speak in Spanish"]').forEach(function(btn) {
      btn.style.display = 'none';
    });
  }
});
```

Also run this after HTMX swaps (since cards are loaded dynamically):

```javascript
document.body.addEventListener('htmx:afterSwap', function(e) {
  if (!window.speechSynthesis) {
    e.detail.target.querySelectorAll('[title="Listen"], [title="Listen to pronunciation"], [title="Listen to example"]').forEach(function(btn) {
      btn.style.display = 'none';
    });
  }
  if (!window.SpeechRecognition && !window.webkitSpeechRecognition) {
    e.detail.target.querySelectorAll('#conv-mic-btn, [title="Speak in Spanish"]').forEach(function(btn) {
      btn.style.display = 'none';
    });
  }
});
```

## Change 8: TTS on sentence_builder and emoji_association

For **sentence_builder**, the correct sentence isn't shown until after submission. But we can add a speak button to the answer feedback. No change needed on the card itself — the feedback template (`flow_feedback.html`) shows the correct answer, and that's where TTS is most useful:

In `templates/partials/flow_feedback.html`, find where the correct answer is displayed and add:

```html
<!-- After showing the correct answer text -->
<button type="button"
  onclick="this.classList.add('speak-active'); speakSpanish('{{ correct_answer | replace("'", "\\'") }}')"
  class="inline ml-1 text-slate-400 hover:text-emerald-300"
  title="Listen">🔊</button>
```

For **emoji_association**, the card already shows the Spanish word options as buttons. Add a speak button on the feedback screen (same as above). Optionally, add TTS to the options themselves — but that might be too noisy. The feedback screen is the best place.

## Summary of what gets a 🔊 button:

| Location | What's spoken | When |
|---|---|---|
| Word intro card | The Spanish word | On click |
| Word intro card | The example sentence | On click |
| Word practice card | The sentence with blank | On click |
| Fill-in-blank card | The sentence with blank | On click |
| MCQ card | The question | On click |
| Conversation AI message | The persona's Spanish message | On click |
| Feedback screen | The correct answer | On click |

## What gets a 🎤 button:

| Location | What it does |
|---|---|
| Conversation input | Records Spanish speech → fills text input → user reviews & sends |

## No backend changes required

Everything is client-side JavaScript using the Web Speech API. The existing HTMX form submission and FastAPI endpoints work as-is — STT just fills the text input that already exists.

## Testing

1. Open the app in Chrome
2. Word intro: verify 🔊 button speaks the word in Spanish
3. Conversation: verify 🔊 on AI messages reads them aloud
4. Conversation: verify 🎤 opens mic, transcribes Spanish, fills input
5. MCQ: verify 🔊 reads the question
6. Open in Firefox: verify mic button is hidden (STT not supported), TTS buttons still work
7. Open on mobile Chrome: verify both TTS and STT work (mic permission prompt appears)
