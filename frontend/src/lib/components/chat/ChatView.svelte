<script lang="ts">
	import { onMount, tick } from 'svelte';
	import { sendMessage, getChatHistory, getPersonas, switchPersona, translateWord } from '$lib/api/chat';
	import type { Persona, ChatMessage, ActivityCard, ChatResponse, PersonasResponse } from '$lib/api/types';
	import InlineFillBlank from './InlineFillBlank.svelte';
	import InlineMcq from './InlineMcq.svelte';
	import InlineFlashcards from './InlineFlashcards.svelte';
	import InlineGrammarNote from './InlineGrammarNote.svelte';
	import InlineQuizSet from './InlineQuizSet.svelte';
	import InlinePlacement from './InlinePlacement.svelte';

	const PERSONA_TINTS: Record<string, { bg: string; border: string; name: string }> = {
		tutor: { bg: '#EDE8F5', border: 'rgba(90,60,140,0.16)', name: '#5A3C8C' },
		marta: { bg: '#F4ECE4', border: 'rgba(168,110,75,0.14)', name: '#8B5A3C' },
		diego: { bg: '#EFEDE2', border: 'rgba(40,90,60,0.18)', name: '#2D5A3D' },
		rosa:  { bg: '#F3E9DC', border: 'rgba(160,80,40,0.18)', name: '#9A4E2C' },
		luis:  { bg: '#EBEDF0', border: 'rgba(40,60,100,0.18)', name: '#3D5A8C' },
	};

	// Conversation items: either a message or an activity card
	interface ConvoItem {
		kind: 'message' | 'card';
		message?: ChatMessage;
		card?: ActivityCard;
	}

	let items = $state<ConvoItem[]>([]);
	let persona = $state<Persona | null>(null);
	let allPersonas = $state<PersonasResponse | null>(null);
	let input = $state('');
	let sending = $state(false);
	let loading = $state(true);
	let chatContainer: HTMLDivElement;
	let personaSwitcherOpen = $state(false);
	let showWelcome = $state(false);

	// Translation tooltip
	let tooltip = $state<{ text: string; translation: string; x: number; y: number } | null>(null);
	let tooltipTimeout: ReturnType<typeof setTimeout>;

	let personaKey = $derived(persona?.id?.toLowerCase() ?? 'marta');
	let tint = $derived(PERSONA_TINTS[personaKey] ?? PERSONA_TINTS.marta);

	onMount(async () => {
		try {
			const [historyRes, personasRes] = await Promise.all([
				getChatHistory(),
				getPersonas(),
			]);
			persona = historyRes.persona;
			allPersonas = personasRes;

			if (historyRes.messages.length === 0) {
				showWelcome = true;
			} else {
				items = historyRes.messages.map(m => ({ kind: 'message' as const, message: m }));
			}
		} catch (e) {
			console.error('Failed to load chat:', e);
		}
		loading = false;
		await scrollToBottom();
	});

	async function send(text?: string) {
		const msg = (text ?? input).trim();
		if (!msg || sending) return;
		input = '';
		showWelcome = false;

		// Add user message
		items = [...items, { kind: 'message', message: { role: 'user', text: msg } }];
		sending = true;
		await scrollToBottom();

		try {
			const res = await sendMessage(msg);
			persona = res.persona;
			appendResponse(res);
		} catch (e) {
			console.error('Chat error:', e);
			items = [...items, {
				kind: 'message',
				message: { role: 'persona', text: 'Something went wrong. Try again?' },
			}];
		}
		sending = false;
		await scrollToBottom();
	}

	function appendResponse(res: ChatResponse) {
		const newItems: ConvoItem[] = [];
		if (res.text) {
			newItems.push({ kind: 'message', message: { role: 'persona', text: res.text } });
		}
		for (const card of res.cards) {
			newItems.push({ kind: 'card', card });
		}
		items = [...items, ...newItems];
	}

	function handleCardComplete(reaction: ChatResponse | null) {
		if (reaction) {
			appendResponse(reaction);
		}
		scrollToBottom();
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter' && !e.shiftKey) {
			e.preventDefault();
			send();
		}
	}

	async function handlePersonaSwitch(personaId: string) {
		personaSwitcherOpen = false;
		if (personaId === persona?.id) return;
		loading = true;
		await switchPersona(personaId);
		// Reload history for the new persona
		const [historyRes, personasRes] = await Promise.all([
			getChatHistory(),
			getPersonas(),
		]);
		persona = historyRes.persona;
		allPersonas = personasRes;
		if (historyRes.messages.length === 0) {
			items = [];
			showWelcome = true;
		} else {
			items = historyRes.messages.map(m => ({ kind: 'message' as const, message: m }));
			showWelcome = false;
		}
		loading = false;
		await scrollToBottom();
	}

	async function scrollToBottom() {
		await tick();
		if (chatContainer) {
			chatContainer.scrollTop = chatContainer.scrollHeight;
		}
	}

	// --- Tap to translate ---
	async function handleWordClick(e: MouseEvent) {
		const target = e.target as HTMLElement;
		if (target.closest('button, input, textarea')) return;
		const bubble = target.closest('.persona-bubble');
		if (!bubble) {
			tooltip = null;
			return;
		}

		const sel = window.getSelection();
		const selectedText = sel?.toString().trim();
		if (selectedText && selectedText.length > 1) {
			await showTranslation(selectedText, bubble.textContent ?? '', e.clientX, e.clientY);
			return;
		}

		const range = document.caretRangeFromPoint(e.clientX, e.clientY);
		if (!range || !bubble.contains(range.startContainer)) return;
		const textNode = range.startContainer;
		if (textNode.nodeType !== Node.TEXT_NODE) return;
		const text = textNode.textContent ?? '';
		let start = range.startOffset;
		let end = range.startOffset;
		const isWordChar = (c: string) => /[\p{L}\p{M}'-]/u.test(c);
		while (start > 0 && isWordChar(text[start - 1])) start--;
		while (end < text.length && isWordChar(text[end])) end++;
		const word = text.slice(start, end).trim();
		if (!word || word.length < 2) return;
		await showTranslation(word, bubble.textContent ?? '', e.clientX, e.clientY);
	}

	async function showTranslation(word: string, context: string, x: number, y: number) {
		tooltip = { text: word, translation: '...', x, y };
		try {
			const res = await translateWord(word, context.slice(0, 200));
			tooltip = { text: word, translation: res.translation, x, y };
		} catch {
			tooltip = null;
		}
		clearTimeout(tooltipTimeout);
		tooltipTimeout = setTimeout(() => { tooltip = null; }, 4000);
	}

	const TUTOR_STARTERS = [
		{ label: '📚 Lesson', message: 'Quiero una lección' },
		{ label: '🧠 Quiz me', message: 'Ponme a prueba con un quiz' },
		{ label: '📝 Vocab', message: 'Enséñame vocabulario nuevo' },
		{ label: '📖 Grammar', message: 'Explícame algo de gramática' },
	];

	const CHAT_STARTERS = [
		{ label: '👋 Say hi', message: '¡Hola! ¿Qué tal?' },
		{ label: '💬 Tell me about you', message: 'Cuéntame algo sobre ti' },
		{ label: '🗣️ Free chat', message: 'Quiero practicar español contigo' },
	];

	let isTutor = $derived(personaKey === 'tutor');
	let STARTERS = $derived(isTutor ? TUTOR_STARTERS : CHAT_STARTERS);
</script>

<!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
<div class="flex flex-col h-full" onclick={handleWordClick} role="application">
	<!-- Header -->
	{#if persona}
		<div class="flex items-center justify-between px-4 py-3" style="background: white; border-bottom: 1px solid rgba(0,0,0,0.06);">
			<button
				class="flex items-center gap-3 transition hover:opacity-80"
				onclick={() => personaSwitcherOpen = !personaSwitcherOpen}
			>
				<div class="w-9 h-9 rounded-full flex items-center justify-center text-sm font-bold"
					style="background: {tint.bg}; color: {tint.name}; border: 1.5px solid {tint.border};">
					{isTutor ? '🎓' : persona.name[0]}
				</div>
				<div class="text-left">
					<p class="text-[15px] font-semibold" style="color: #1a1410; letter-spacing: -0.2px;">{persona.name}</p>
					<p class="text-[11px]" style="color: rgba(60,45,30,0.55);">{persona.region} &middot; online</p>
				</div>
				<svg class="ml-1" width="10" height="6" viewBox="0 0 10 6" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" style="color: rgba(60,45,30,0.4);">
					<path d="M1 1l4 4 4-4"/>
				</svg>
			</button>
		</div>
	{/if}

	<!-- Messages -->
	<div bind:this={chatContainer} class="flex-1 min-h-0 overflow-y-auto px-3.5 py-3 space-y-2.5" style="background: #FBF7F0;">
		{#if loading}
			<div class="flex items-center justify-center py-20">
				<div class="h-8 w-8 animate-spin rounded-full border-4 border-t-transparent" style="border-color: rgba(200,85,61,0.2); border-top-color: transparent;"></div>
			</div>
		{:else if showWelcome && persona}
			<!-- Welcome screen -->
			<div class="flex flex-col items-center justify-center py-12 space-y-4">
				<div class="w-16 h-16 rounded-full flex items-center justify-center text-2xl font-bold"
					style="background: {tint.bg}; color: {tint.name}; border: 2px solid {tint.border};">
					{isTutor ? '🎓' : persona.name[0]}
				</div>
				<div class="text-center">
					<p class="text-xl font-bold" style="color: #1a1410; font-family: var(--font-serif);">{persona.name}</p>
					<p class="text-sm mt-0.5" style="color: rgba(60,45,30,0.55);">{isTutor ? persona.welcome_sub : `${persona.region} · ${persona.welcome_sub}`}</p>
				</div>
				<div class="flex flex-wrap gap-2 justify-center mt-3">
					{#each STARTERS as s}
						<button
							class="rounded-full px-4 py-2 text-sm font-semibold transition active:scale-95"
							style="background: white; color: {tint.name}; border: 1px solid {tint.border}; box-shadow: 0 1px 3px rgba(0,0,0,0.04);"
							onclick={() => send(s.message)}
						>
							{s.label}
						</button>
					{/each}
				</div>
			</div>
		{:else}
			{#each items as item, i}
				{#if item.kind === 'message' && item.message}
					<div class="flex {item.message.role === 'user' ? 'justify-end' : 'justify-start'}">
						<div
							class="max-w-[80%] px-3.5 py-2.5 text-[15.5px] leading-relaxed {item.message.role === 'persona' ? 'persona-bubble' : ''}"
							style={item.message.role === 'persona'
								? `background: ${tint.bg}; border: 1px solid ${tint.border}; border-radius: 20px 20px 20px 6px; color: #1a1410;`
								: 'background: #C8553D; border-radius: 20px 20px 6px 20px; color: white;'}
						>
							{#if item.message.role === 'persona' && persona && (i === 0 || items[i-1]?.message?.role !== 'persona')}
								<p class="text-[11px] font-semibold mb-1" style="color: {tint.name}; font-family: var(--font-serif);">{persona.name}</p>
							{/if}
							<p class="whitespace-pre-wrap">{item.message.text}</p>
						</div>
					</div>
				{:else if item.kind === 'card' && item.card}
					<div class="my-2">
						{#if item.card.type === 'fill_blank'}
							<InlineFillBlank card={item.card} personaColor={tint.name} onComplete={handleCardComplete} />
						{:else if item.card.type === 'mcq'}
							<InlineMcq card={item.card} personaColor={tint.name} onComplete={handleCardComplete} />
						{:else if item.card.type === 'flashcard_set'}
							<InlineFlashcards card={item.card} personaColor={tint.name} />
						{:else if item.card.type === 'grammar_note'}
							<InlineGrammarNote card={item.card} personaColor={tint.name} />
						{:else if item.card.type === 'quiz_set'}
							<InlineQuizSet card={item.card} personaColor={tint.name} onComplete={handleCardComplete} />
						{:else if item.card.type === 'placement'}
							<InlinePlacement card={item.card} personaColor={tint.name} onComplete={handleCardComplete} />
						{/if}
					</div>
				{/if}
			{/each}

			{#if sending}
				<div class="flex justify-start">
					<div class="rounded-2xl px-4 py-3" style="background: {tint.bg}; border: 1px solid {tint.border}; border-radius: 20px 20px 20px 6px;">
						<div class="flex gap-1.5">
							<span class="w-2 h-2 rounded-full" style="background: {tint.name}; animation: dot-pulse 1s infinite 0ms;"></span>
							<span class="w-2 h-2 rounded-full" style="background: {tint.name}; animation: dot-pulse 1s infinite 160ms;"></span>
							<span class="w-2 h-2 rounded-full" style="background: {tint.name}; animation: dot-pulse 1s infinite 320ms;"></span>
						</div>
					</div>
				</div>
			{/if}
		{/if}
	</div>

	<!-- Composer -->
	{#if !loading}
		<div class="shrink-0" style="background: white; border-top: 1px solid rgba(0,0,0,0.06);">
			<!-- Starter buttons — always visible -->
			<div class="flex gap-1.5 px-3 pt-2.5 pb-1 overflow-x-auto" style="scrollbar-width: none;">
				{#each STARTERS as s}
					<button
						class="shrink-0 rounded-full px-3 py-1.5 text-[12px] font-semibold transition active:scale-95 whitespace-nowrap"
						style="background: #FBF7F0; color: {tint.name}; border: 1px solid {tint.border};"
						onclick={() => send(s.message)}
						disabled={sending}
					>
						{s.label}
					</button>
				{/each}
			</div>
			<!-- Input row -->
			<div class="px-3 pt-1 pb-3 flex gap-2">
				<input
					type="text"
					bind:value={input}
					onkeydown={handleKeydown}
					placeholder="Escribe algo..."
					disabled={sending}
					class="flex-1 rounded-full px-4 py-2.5 text-[15px] outline-none transition disabled:opacity-50"
					style="background: #FBF7F0; border: 0.5px solid rgba(0,0,0,0.08); color: #1a1410;"
				/>
				<button
					onclick={() => send()}
					disabled={!input.trim() || sending}
					class="w-[34px] h-[34px] rounded-full flex items-center justify-center transition active:scale-95 disabled:opacity-40 self-end"
					style="background: #C8553D; color: white;"
					aria-label="Send message"
				>
					<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
						<line x1="22" y1="2" x2="11" y2="13"></line>
						<polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
					</svg>
				</button>
			</div>
		</div>
	{/if}

	<!-- Persona Switcher Bottom Sheet -->
	{#if personaSwitcherOpen && allPersonas}
		<div class="fixed inset-0 z-50">
			<!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
			<div class="absolute inset-0 bg-black/20" onclick={() => personaSwitcherOpen = false} role="presentation"></div>
			<div class="absolute bottom-0 left-0 right-0 rounded-t-2xl px-5 py-4 space-y-3 animate-slide-up" style="background: white; max-height: 60vh; overflow-y: auto;">
				<div class="w-10 h-1 rounded-full mx-auto mb-2" style="background: rgba(0,0,0,0.1);"></div>
				<h3 class="text-lg font-bold" style="color: #1a1410; font-family: var(--font-serif);">Who do you want to talk to?</h3>
				{#each Object.entries(allPersonas.personas) as [pid, p]}
					{@const isActive = pid === persona?.id}
					{@const pTint = PERSONA_TINTS[pid] ?? PERSONA_TINTS.marta}
					<button
						class="w-full flex items-center gap-3 p-3 rounded-xl transition"
						style="background: {isActive ? pTint.bg : 'transparent'}; border: 1px solid {isActive ? pTint.border : 'transparent'};"
						onclick={() => handlePersonaSwitch(pid)}
					>
						<div class="w-10 h-10 rounded-full flex items-center justify-center text-sm font-bold shrink-0"
							style="background: {pTint.bg}; color: {pTint.name}; border: 1.5px solid {pTint.border};">
							{pid === 'tutor' ? '🎓' : p.name[0]}
						</div>
						<div class="text-left flex-1 min-w-0">
							<p class="text-sm font-bold" style="color: #1a1410;">{p.name}</p>
							<p class="text-xs truncate" style="color: rgba(60,45,30,0.55);">{p.bio}</p>
						</div>
						{#if isActive}
							<span class="text-[10px] font-bold shrink-0" style="color: {pTint.name};">online</span>
						{/if}
					</button>
				{/each}
			</div>
		</div>
	{/if}

	<!-- Translation Tooltip -->
	{#if tooltip}
		<div
			class="fixed z-[60] rounded-lg px-3 py-1.5 text-sm pointer-events-none"
			style="background: #1a1410; color: white; left: {Math.min(tooltip.x, (typeof window !== 'undefined' ? window.innerWidth : 400) - 140)}px; top: {tooltip.y - 44}px; transform: translateX(-50%); box-shadow: 0 4px 12px rgba(0,0,0,0.2);"
		>
			{tooltip.translation}
			<span class="ml-1.5 text-xs opacity-60">{tooltip.text}</span>
		</div>
	{/if}
</div>

<style>
	@keyframes animate-slide-up {
		from { transform: translateY(100%); }
		to { transform: translateY(0); }
	}
	.animate-slide-up {
		animation: animate-slide-up 0.3s ease-out;
	}
</style>
