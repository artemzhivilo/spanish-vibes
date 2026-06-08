<script lang="ts">
	import { onMount, tick } from 'svelte';
	import { cn } from '$lib/utils/cn';
	import { api } from '$lib/api/client';

	interface Message {
		role: 'ai' | 'user' | 'system';
		content: string;
		corrections?: Array<{ original: string; corrected: string; explanation: string }>;
	}

	interface Props {
		sessionId: number;
		conceptId: string;
		conceptName: string;
		topic?: string;
		difficulty?: number;
		conversationType?: string;
		onComplete: () => void;
	}

	let {
		sessionId,
		conceptId,
		conceptName,
		topic = '',
		difficulty = 1,
		conversationType = '',
		onComplete,
	}: Props = $props();

	const PERSONA_TINTS: Record<string, { bg: string; border: string; name: string }> = {
		marta: { bg: '#F4ECE4', border: 'rgba(168,110,75,0.14)', name: '#8B5A3C' },
		diego: { bg: '#EFEDE2', border: 'rgba(40,90,60,0.18)', name: '#2D5A3D' },
		rosa:  { bg: '#F3E9DC', border: 'rgba(160,80,40,0.18)', name: '#9A4E2C' },
		luis:  { bg: '#EBEDF0', border: 'rgba(40,60,100,0.18)', name: '#3D5A8C' },
	};

	let messages = $state<Message[]>([]);
	let conversationId = $state<number | null>(null);
	let personaName = $state('');
	let input = $state('');
	let sending = $state(false);
	let ended = $state(false);
	let hint = $state('');
	let chatContainer: HTMLDivElement;
	let menuOpen = $state(false);

	let personaKey = $derived(personaName.toLowerCase());
	let tint = $derived(PERSONA_TINTS[personaKey] ?? PERSONA_TINTS.marta);

	onMount(async () => {
		const res = await api.post<{
			conversation_id: number;
			persona_name: string;
			messages: Array<{ role: string; content: string }>;
		}>('/flow/conversation/start', {
			session_id: sessionId,
			concept_id: conceptId,
			topic,
			difficulty,
			conversation_type: conversationType,
		});
		conversationId = res.conversation_id;
		personaName = res.persona_name;
		messages = res.messages.map(m => ({ role: m.role as Message['role'], content: m.content }));
	});

	async function send() {
		if (!input.trim() || sending || ended || !conversationId) return;

		const userMessage = input.trim();
		input = '';
		messages = [...messages, { role: 'user', content: userMessage }];
		sending = true;
		await scrollToBottom();

		const res = await api.post<{
			ai_reply: string | null;
			is_ended: boolean;
			corrections: Array<{ original: string; corrected: string; explanation: string }>;
			hint: string;
			translation: { display_message: string } | null;
			persona_name: string;
		}>('/flow/conversation/respond', {
			session_id: sessionId,
			conversation_id: conversationId,
			message: userMessage,
		});

		if (res.corrections?.length) {
			const lastIdx = messages.length - 1;
			messages[lastIdx] = { ...messages[lastIdx], corrections: res.corrections };
		}

		if (res.translation) {
			messages = [...messages, { role: 'system', content: res.translation.display_message }];
		}

		if (res.ai_reply) {
			messages = [...messages, { role: 'ai', content: res.ai_reply }];
		}

		hint = res.hint || '';
		ended = res.is_ended;
		sending = false;
		await scrollToBottom();
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter' && !e.shiftKey) {
			e.preventDefault();
			send();
		}
	}

	async function scrollToBottom() {
		await tick();
		if (chatContainer) {
			chatContainer.scrollTop = chatContainer.scrollHeight;
		}
	}

	async function skip() {
		if (!conversationId) return;
		await api.post(`/flow/conversation/skip?session_id=${sessionId}&conversation_id=${conversationId}`);
		onComplete();
	}
</script>

<div class="rounded-2xl overflow-hidden flex flex-col max-h-[70vh]" style="background: white; box-shadow: 0 1px 0 rgba(0,0,0,0.02), 0 4px 14px rgba(0,0,0,0.04);">
	<!-- Header -->
	<div class="flex items-center justify-between px-4 py-3" style="border-bottom: 1px solid rgba(0,0,0,0.06);">
		<div class="flex items-center gap-3">
			<div class="w-9 h-9 rounded-full flex items-center justify-center text-sm font-bold" style="background: {tint.bg}; color: {tint.name}; border: 1.5px solid {tint.border};">
				{personaName ? personaName[0] : '?'}
			</div>
			<div>
				<p class="text-[15px] font-semibold" style="color: #1a1410; letter-spacing: -0.2px;">{personaName || 'Loading...'}</p>
				<p class="text-[11px]" style="color: rgba(60,45,30,0.55);">{conceptName}</p>
			</div>
		</div>
		<div class="relative">
			<button
				class="w-8 h-8 flex items-center justify-center rounded-lg transition hover:bg-black/5"
				style="color: rgba(60,45,30,0.7);"
				onclick={() => menuOpen = !menuOpen}
				aria-label="Conversation options"
			>
				<svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
					<circle cx="8" cy="3" r="1.5" />
					<circle cx="8" cy="8" r="1.5" />
					<circle cx="8" cy="13" r="1.5" />
				</svg>
			</button>
			{#if menuOpen}
				<div
					class="absolute right-0 top-10 z-50 min-w-[160px] rounded-xl overflow-hidden py-1"
					style="background: white; border: 1px solid rgba(0,0,0,0.08); box-shadow: 0 12px 32px rgba(0,0,0,0.12);"
					role="menu"
				>
					<button
						class="w-full text-left px-4 py-2.5 text-sm transition hover:bg-black/5"
						style="color: #1a1410;"
						onclick={() => { menuOpen = false; skip(); }}
						role="menuitem"
					>
						Skip conversation
					</button>
					<button
						class="w-full text-left px-4 py-2.5 text-sm transition hover:bg-black/5"
						style="color: #C8553D;"
						onclick={() => { menuOpen = false; ended = true; }}
						role="menuitem"
					>
						End conversation
					</button>
				</div>
				<button
					class="fixed inset-0 z-40"
					onclick={() => menuOpen = false}
					aria-label="Close menu"
				></button>
			{/if}
		</div>
	</div>

	<!-- Messages -->
	<div bind:this={chatContainer} class="flex-1 overflow-y-auto px-3.5 py-3 space-y-2.5 min-h-[200px]" style="background: #FBF7F0;">
		{#each messages as msg, i}
			<div class={cn('flex', msg.role === 'user' ? 'justify-end' : 'justify-start')}>
				<div
					class="max-w-[80%] px-3.5 py-2.5 text-[15.5px] leading-relaxed"
					style={msg.role === 'ai'
						? `background: ${tint.bg}; border: 1px solid ${tint.border}; border-radius: 20px 20px 20px 6px; color: #1a1410;`
						: msg.role === 'user'
						? 'background: #C8553D; border-radius: 20px 20px 6px 20px; color: white;'
						: 'background: rgba(200,85,61,0.08); border-radius: 12px; color: rgba(60,45,30,0.7); font-size: 13px; font-style: italic;'}
				>
					{#if msg.role === 'ai' && personaName && (i === 0 || messages[i-1]?.role !== 'ai')}
						<p class="text-[11px] font-semibold mb-1" style="color: {tint.name}; font-family: var(--font-serif);">{personaName}</p>
					{/if}
					<p class="whitespace-pre-wrap">{msg.content}</p>
					{#if msg.corrections?.length}
						<div class="mt-2 pt-2 space-y-1" style="border-top: 1px solid rgba(0,0,0,0.08);">
							{#each msg.corrections as c}
								<p class="text-xs">
									<span style="color: #C8553D; text-decoration: line-through;">{c.original}</span>
									<span style="color: rgba(60,45,30,0.4);" class="mx-1">&rarr;</span>
									<span style="color: #2D5A3D;">{c.corrected}</span>
								</p>
								{#if c.explanation}
									<p class="text-[10px]" style="color: rgba(60,45,30,0.55);">{c.explanation}</p>
								{/if}
							{/each}
						</div>
					{/if}
				</div>
			</div>
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
	</div>

	<!-- Hint -->
	{#if hint && !ended}
		<div class="px-4 pb-1" style="background: white;">
			<p class="text-[11px] italic" style="color: rgba(60,45,30,0.55);">Hint: {hint}</p>
		</div>
	{/if}

	<!-- Input or End -->
	{#if ended}
		<div class="px-4 py-3" style="border-top: 1px solid rgba(0,0,0,0.06);">
			<button
				class="w-full rounded-xl py-3 text-center font-bold text-white transition active:scale-[0.98]"
				style="background: #C8553D;"
				onclick={onComplete}
			>
				Continue
			</button>
		</div>
	{:else}
		<div class="px-3 py-3 flex gap-2" style="border-top: 1px solid rgba(0,0,0,0.06); background: white;">
			<input
				type="text"
				bind:value={input}
				onkeydown={handleKeydown}
				placeholder="Escribe algo..."
				disabled={sending}
				class="flex-1 rounded-full px-4 py-2.5 text-[15.5px] outline-none transition disabled:opacity-50"
				style="background: #FBF7F0; border: 0.5px solid rgba(0,0,0,0.08); color: #1a1410;"
			/>
			<button
				onclick={send}
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
		<p class="text-center pb-2 text-[11px]" style="color: rgba(60,45,30,0.45); background: white;">
			Tap a Spanish word to translate
		</p>
	{/if}
</div>
