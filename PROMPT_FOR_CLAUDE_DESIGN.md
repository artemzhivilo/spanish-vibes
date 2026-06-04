# Spanish Vibes — Prompt for Claude Design

> Paste the section below the divider into Claude Design as a single brief. The bottom of this file has notes on how to use it and what to push back on.

---

# Brief: Spanish Vibes

Design an interactive prototype for a Spanish-learning app called **Spanish Vibes**. This is a mobile-first web app (also works on desktop). I want to see the chat experience, the inline activity cards, the persona switch, and the session-end summary — clickable and connected.

## The pitch in one line

It's not Duolingo and it's not a chatbot. It's the experience of texting a Spanish friend who happens to be a teacher.

## The vibe — read this first, everything else serves it

Open the app. There's already a chat going. Marta has just sent: *"¡Hola! ¿Qué tal tu fin de semana?"* — because she remembers from last time that I went hiking on Saturday. I reply, in mixed Spanish + English. She corrects me gently inside her response, no red pen, no popup. Three messages later, the chat shows a tiny inline card: four sentences about trails, fill in the verb. I tap through it in 20 seconds, she reacts to my answers, the conversation continues. Twenty minutes have passed and I've practiced four grammar concepts and learned six new words without ever opening a "lesson."

That is the entire product. Everything below describes the surfaces that produce that feeling.

## Visual mood

- **Texture:** like a beautifully designed messaging app, not a learning app. Closer to iMessage, Telegram, or Beeper than to Duolingo. The chat is the canvas.
- **Palette:** warm and soft. Off-white background, warm dark text, a single accent color (think terracotta or muted amber — Spanish-feeling without being a flag cliché). Persona avatars and persona-tinted bubbles add color, not the chrome.
- **Typography:** rounded, friendly sans-serif for chat. A small accent serif for one or two moments (header, lesson card title) to make it feel curated, not generic.
- **Density:** generous. One thought per bubble. White space matters. This is not a dashboard.
- **Motion:** subtle and physical. Bubbles fade and rise. Activity cards slide in like a friend handing you a napkin. No confetti, no big celebrations. A correct answer just glows for half a beat.
- **What to avoid:** owls, mascots, gem currencies, streak flames, cartoon palettes, big rounded green buttons, "+5 XP" floaters. None of that. The aesthetic is "smart adult app," not "language game."

## Form factor

Mobile-first portrait phone screens, ~390pt wide. Show a desktop variant for the "Today" / session summary screen if there's time, but the chat experience is mobile.

## Screens to design

### 1. Onboarding (3 screens)
- **Welcome:** logo, tagline ("Spanish, in conversation"), one button "Start chatting." That's it.
- **Pick a vibe:** four persona cards (see below). User picks one to start. Cards show name, photo/illustration, a one-line voice sample, and a vibe tag ("patient teacher" / "loud football fan" / "warm grandmother" / "tech bro").
- **First message:** chat opens with the chosen persona greeting them and asking one question. No tutorial overlay, no popups.

### 2. Chat (the main surface)
This is where 90% of the app lives. Show several variants of this screen so it's clear how the chat fluidly mixes content types:

- **Plain chat exchange.** User and persona texting back and forth. User's bubbles right-aligned in accent color. Persona bubbles left-aligned with avatar, slightly tinted background.
- **Chat with a gentle correction woven in.** Show how the persona corrects without breaking flow — e.g. user wrote *"yo tiene un perro"*, persona's reply naturally restates "*ah, **tienes** un perro — ¿cómo se llama?*" with the corrected word subtly highlighted on a long-press / hover. No red pen, no error popup.
- **Chat with an inline `fill_in_blank` card.** A small card sits inline between bubbles. 3–4 short Spanish sentences with one word missing per sentence. User types or taps. Card stays inline forever — it doesn't take over the screen. After completing, the persona sends a reaction bubble.
- **Chat with an inline `flashcard_set` card.** A small swipeable card stack of 4–6 word pairs the persona "wants you to look at." Tap to flip, swipe to dismiss. Compact.
- **Chat with an inline `grammar_explainer` card.** A clean card titled with a rule, two example sentences, one sentence of plain-language explanation. Optional "show more" expander.
- **Chat in roleplay mode.** A small banner at the top of the chat says *"Roleplay: ordering at a café — Marta is the waitress."* Bubbles continue as normal but the banner gives context. A small "leave roleplay" affordance.
- **Word lookup.** User long-presses a Spanish word in a persona's bubble. A small definition popover slides up from the bottom: word, translation, one example, "got it" button.

### 3. Persona switcher
Pulldown or sheet from the top of the chat. Shows the four personas as cards. Each shows a tiny "last seen" subtitle ("Marta — chatted yesterday", "Diego — new"). Tapping one starts a fresh chat with that persona, but the user's profile and progress carry over (the new persona greets the user by name and references something they know).

### 4. Today / Session summary
End of a session screen, also reachable from a "Today" tab. Quiet, generous layout:
- A one-line celebration ("Nice 23-minute chat with Marta.") — no exclamation marks, no "+200 XP".
- A small section: "Words you used for the first time" — 4–6 word chips.
- A small section: "Things to come back to" — 1–2 grammar points the persona noted.
- A small section: "What Marta remembered about you" — 1–2 lines pulled from the persona's notes ("you mentioned a hike on Saturday").
- One subtle button: "Keep chatting" or "Pick a different vibe."

### 5. Profile (minimal)
A single screen: user's name, current level (a soft chip like "around A2"), recent topics they've talked about (chips: "hiking", "food", "work"), and a list of personas they've met with affinity dots. No graphs, no streak counts, no badges.

## The four personas (these are the soul — design them as characters, not skins)

- **Marta** — friendly teacher type. Warm, patient, asks follow-ups. Default for new users. Voice sample: *"Cuéntame, ¿cómo fue tu día?"*
- **Diego** — football-obsessed uni student. Slang-heavy, high energy, uses "tío" a lot. Voice sample: *"Tío, ayer el partido fue una locura, ¿lo viste?"*
- **Abuela Rosa** — warm grandmother. Cooking, family, traditional expressions. Voice sample: *"Mi vida, ¿has comido algo rico hoy?"*
- **Luis** — Madrid tech startup guy. Talks fast, mixes in English loanwords. Voice sample: *"Ostras, hoy tuvimos un meeting eterno con el equipo de product."*

Each persona's chat bubbles should have a faint personality cue — slightly different bubble tint, an avatar that reads as a person not a logo, and consistent voice in their messages. Marta and Diego should look as different as a teacher and a football fan would in real life.

## What's deliberately not in v1

Don't design any of this — and resist the urge to add them:
- Course tree, syllabus, "Section 1 Unit 3" structure
- Streaks, daily goals, leagues, leaderboards, XP, badges
- Settings screen (we don't need one yet)
- Push notifications UI
- Multi-device sync indicators
- Auth / sign-up / account screens (assume signed-in)
- TTS / voice / pronunciation UI

## What "good" looks like for this prototype

When I click through the prototype I should feel:
- This is something I'd actually open every day, not something I'd grind through.
- The chat is the surface and the activities are *served by* the chat, not the other way around.
- The four personas feel like real people with different vibes, not four costumes on the same character.
- I am respected as an adult learner. There is no condescension.

If you're tempted to add a "Lessons" tab, a progress chart, or a streak counter, stop and re-read "the vibe."

## Inspiration / references

- The chat surface should feel closer to iMessage / Beeper / Telegram than to any language app.
- The summary screen should feel closer to a Strava run summary than a Duolingo end-of-lesson screen — grown-up, factual, kind.
- The persona cards should feel like Spotify artist pages — warmth, character, personality.

---

# How to use this prompt with Claude Design

1. Open Claude Design at claude.ai/design. (Pro/Max/Team/Enterprise required — research preview.)
2. Paste the brief above (everything between the two `---` markers) as a single message.
3. Iterate. Claude Design works best with at least 2–3 rounds of follow-ups. Once it returns a first prototype, give it specific feedback like:
   - *"Marta's bubble color is too saturated — desaturate by 30%."*
   - *"The fill-in-the-blank card is too tall. Compress it to a single visual row of 3 small inputs."*
   - *"Make Diego's bubble look more like a football fan would design a bubble — keep it tasteful but a little louder."*

## What to push back on if you see it in the output

- **Personas treated as cosmetic skins** — the same bubble with a different name. Push: "Marta and Diego should *feel* different, not just look slightly different."
- **A 'Lessons' tab sneaking in** — Claude Design has seen a thousand language apps and will want to add one. Cut it every time.
- **Gamification creeping back** — XP counters, streak flames, level-up animations. Cut all of it.
- **Activity cards taking over the chat** — they should sit *inline* like a message, not push the conversation off-screen.
- **Bland persona avatars** — generic illustrated heads. Push for character: Marta could be a real photo, Diego could have a football kit detail, Abuela Rosa could have a kitchen behind her.

## Things you might want to tweak before pasting

- If you want **desktop-first** instead, swap the Form Factor section.
- If you have **specific colors** in mind, replace the palette description with hex values.
- If you want **a different persona lineup** (drop one, add a sarcastic teenager, etc.), edit the personas section — that's the part most likely to drift in iteration anyway.
- If you want Claude Design to **also mock up the desktop "Today" dashboard**, expand screen 4.
