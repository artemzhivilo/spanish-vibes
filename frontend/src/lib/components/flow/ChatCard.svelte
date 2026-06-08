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

	let messages = $state<Message[]>([]);
	let conversationId = $state<number | null>(null);
	let personaName = $state('');
	let input = $state('');
	let sending = $state(false);
	let ended = $state(false);
	let hint = $state('');
	let chatContainer: HTMLDivElement;

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

<div class="rounded-2xl bg-[#1a2d35] shadow-lg shadow-black/20 overflow-hidden flex flex-col max-h-[70vh]">
	<!-- Header -->
	<div class="flex items-center justify-between px-4 py-3 bg-[#0f1a1f]">
		<div class="flex items-center gap-2">
			<span class="text-xs font-bold uppercase tracking-wider text-violet-400">Chat</span>
			{#if personaName}
				<span class="text-xs font-bold text-slate-400">with {personaName}</span>
			{/if}
		</div>
		<div class="flex items-center gap-2">
			<span class="text-[10px] font-bold text-slate-500">{conceptName}</span>
			<button
				class="text-xs text-slate-500 hover:text-slate-300 transition"
				onclick={skip}
			>
				Skip
			</button>
		</div>
	</div>

	<!-- Messages -->
	<div bind:this={chatContainer} class="flex-1 overflow-y-auto px-4 py-3 space-y-3 min-h-[200px]">
		{#each messages as msg}
			<div class={cn('flex', msg.role === 'user' ? 'justify-end' : 'justify-start')}>
				<div class={cn(
					'max-w-[80%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed',
					msg.role === 'ai' && 'bg-[#0f1a1f] text-slate-200 rounded-bl-md',
					msg.role === 'user' && 'bg-emerald-600/20 text-emerald-100 rounded-br-md',
					msg.role === 'system' && 'bg-amber-500/10 text-amber-300/80 text-xs italic rounded-lg',
				)}>
					{#if msg.role === 'ai' && personaName}
						<p class="text-[10px] font-bold text-violet-400/60 mb-1">{personaName}</p>
					{/if}
					<p class="whitespace-pre-wrap">{msg.content}</p>
					{#if msg.corrections?.length}
						<div class="mt-2 pt-2 border-t border-red-500/20 space-y-1">
							{#each msg.corrections as c}
								<p class="text-xs">
									<span class="text-red-400 line-through">{c.original}</span>
									<span class="text-slate-500 mx-1">&rarr;</span>
									<span class="text-emerald-400">{c.corrected}</span>
								</p>
								{#if c.explanation}
									<p class="text-[10px] text-slate-500">{c.explanation}</p>
								{/if}
							{/each}
						</div>
					{/if}
				</div>
			</div>
		{/each}

		{#if sending}
			<div class="flex justify-start">
				<div class="bg-[#0f1a1f] rounded-2xl rounded-bl-md px-4 py-3">
					<div class="flex gap-1">
						<span class="w-2 h-2 bg-slate-500 rounded-full animate-bounce" style="animation-delay: 0ms"></span>
						<span class="w-2 h-2 bg-slate-500 rounded-full animate-bounce" style="animation-delay: 150ms"></span>
						<span class="w-2 h-2 bg-slate-500 rounded-full animate-bounce" style="animation-delay: 300ms"></span>
					</div>
				</div>
			</div>
		{/if}
	</div>

	<!-- Hint -->
	{#if hint && !ended}
		<div class="px-4 pb-1">
			<p class="text-[11px] text-amber-400/60 italic">Hint: {hint}</p>
		</div>
	{/if}

	<!-- Input or End -->
	{#if ended}
		<div class="px-4 py-3 border-t border-[#1e3a47]">
			<button
				class="w-full rounded-xl bg-emerald-500 py-3 text-center font-black text-emerald-950 transition hover:bg-emerald-400 active:scale-[0.98]"
				onclick={onComplete}
			>
				Continue
			</button>
		</div>
	{:else}
		<div class="px-3 py-3 border-t border-[#1e3a47] flex gap-2">
			<input
				type="text"
				bind:value={input}
				onkeydown={handleKeydown}
				placeholder="Escribe en espa&ntilde;ol..."
				disabled={sending}
				class="flex-1 rounded-xl bg-[#0f1a1f] border-2 border-[#1e3a47] px-4 py-2.5 text-sm text-slate-100 placeholder-slate-500 outline-none focus:border-emerald-500 transition disabled:opacity-50"
			/>
			<button
				onclick={send}
				disabled={!input.trim() || sending}
				class="rounded-xl bg-emerald-500 px-4 py-2.5 font-bold text-emerald-950 transition hover:bg-emerald-400 disabled:opacity-40 disabled:hover:bg-emerald-500 active:scale-95"
			>
				Send
			</button>
		</div>
	{/if}
</div>
