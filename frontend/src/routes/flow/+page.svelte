<script lang="ts">
	import { onMount } from 'svelte';
	import { startSession, getNextCard, submitAnswer, markTeachSeen } from '$lib/api/flow';
	import type { FlowCard, AnswerResponse } from '$lib/api/types';
	import McqCard from '$lib/components/flow/McqCard.svelte';
	import TeachCard from '$lib/components/flow/TeachCard.svelte';
	import ChatCard from '$lib/components/flow/ChatCard.svelte';
	import LoadingCard from '$lib/components/flow/LoadingCard.svelte';

	let loading = $state(true);
	let sessionId = $state(0);
	let streak = $state(0);
	let conceptsMastered = $state(0);
	let totalConcepts = $state(0);
	let cardsAnswered = $state(0);
	let cefr = $state('A1');

	let currentCard = $state<FlowCard | null>(null);
	let conceptName = $state('');
	let cardStartTime = $state(0);
	let loadingCard = $state(false);
	let showCelebration = $state(false);
	let celebrationText = $state('');

	const CELEBRATION_MILESTONES = [5, 10, 15, 20, 25, 50];

	const CHAT_CARD_TYPES = new Set(['conversation', 'story_comprehension']);
	const QUIZ_CARD_TYPES = new Set([
		'mcq', 'word_practice', 'word_intro', 'word_match',
		'sentence_builder', 'emoji_association', 'fill_blank',
	]);

	onMount(async () => {
		try {
			const session = await startSession();
			sessionId = session.session_id;
			streak = session.streak;
			conceptsMastered = session.concepts_mastered;
			totalConcepts = session.total_concepts;
			cardsAnswered = session.cards_answered;
			cefr = session.cefr;
			loading = false;
			await loadNextCard();
		} catch (e) {
			console.error('Failed to start session:', e);
			loading = false;
		}
	});

	async function loadNextCard() {
		loadingCard = true;
		currentCard = null;

		let retries = 0;
		while (retries < 4) {
			const res = await getNextCard(sessionId, retries);
			if (res.status === 'ok' && res.card) {
				currentCard = res.card;
				conceptName = res.concept_name ?? '';
				cardStartTime = Date.now();
				loadingCard = false;
				return;
			}
			if (res.status === 'loading') {
				retries = res.retry ?? retries + 1;
				await new Promise(r => setTimeout(r, 400));
				continue;
			}
			break;
		}
		loadingCard = false;
	}

	async function handleAnswer(chosenOption: string): Promise<AnswerResponse> {
		const res = await submitAnswer(sessionId, chosenOption, currentCard!, cardStartTime);

		streak = res.streak;
		cardsAnswered = res.cards_answered;
		conceptsMastered = res.concepts_mastered;
		totalConcepts = res.total_concepts;

		if (CELEBRATION_MILESTONES.includes(res.streak)) {
			celebrationText = `${res.streak} streak!`;
			showCelebration = true;
			setTimeout(() => { showCelebration = false; }, 1500);
		}

		return res;
	}

	async function handleTeachSeen() {
		if (!currentCard) return;
		await markTeachSeen(sessionId, currentCard.concept_id);
		await loadNextCard();
	}
</script>

<svelte:head>
	<title>Spanish Vibes - Flow</title>
</svelte:head>

<div class="flex flex-col items-center gap-3 max-w-[42rem] mx-auto">
	<!-- Compact flow header -->
	<div class="w-full flex items-center justify-between">
		<div class="flex items-center gap-3">
			<div class="flex items-center gap-1" title="Streak">
				<span class="text-lg" class:opacity-30={streak === 0}>🔥</span>
				<span class="text-base font-black text-amber-400">{streak}</span>
			</div>
			<span class="text-xs text-slate-500 font-bold">{conceptsMastered}/{totalConcepts}</span>
			<span class="hidden sm:inline rounded-full bg-amber-500/15 px-2 py-0.5 text-[10px] font-bold text-amber-300">
				{cefr}
			</span>
		</div>
		<div class="flex items-center gap-2">
			<span class="text-xs text-slate-500">{cardsAnswered} cards</span>
			<a
				href="/"
				class="rounded-full bg-slate-500/15 w-7 h-7 flex items-center justify-center text-xs font-bold text-slate-400 transition hover:bg-slate-500/25 hover:text-slate-200"
				title="Exit"
			>
				&times;
			</a>
		</div>
	</div>

	<!-- Card slot -->
	<div class="w-full">
		{#if loading || loadingCard}
			<LoadingCard />
		{:else if currentCard?.card_type === 'teach'}
			<TeachCard card={currentCard} {conceptName} onContinue={handleTeachSeen} />
		{:else if currentCard && CHAT_CARD_TYPES.has(currentCard.card_type)}
			<ChatCard
				{sessionId}
				conceptId={currentCard.concept_id}
				{conceptName}
				topic={currentCard.interest_topics?.[0] ?? ''}
				difficulty={currentCard.difficulty}
				conversationType={currentCard.conversation_type}
				onComplete={loadNextCard}
			/>
		{:else if currentCard && (QUIZ_CARD_TYPES.has(currentCard.card_type) || currentCard.options?.length)}
			<McqCard
				card={currentCard}
				{conceptName}
				onAnswer={handleAnswer}
				onNext={loadNextCard}
			/>
		{:else if currentCard}
			<!-- Fallback for unrecognized card types — treat as quiz -->
			<McqCard
				card={currentCard}
				{conceptName}
				onAnswer={handleAnswer}
				onNext={loadNextCard}
			/>
		{:else}
			<div class="rounded-2xl bg-[#1a2d35] p-6 shadow-lg shadow-black/20 text-center">
				<p class="text-slate-400 mb-2">No more cards right now</p>
				<p class="text-sm text-slate-500">Come back later for more practice</p>
				<a href="/" class="mt-4 inline-block rounded-xl bg-emerald-500 px-6 py-2.5 font-bold text-emerald-950">
					Back Home
				</a>
			</div>
		{/if}
	</div>

	<!-- Celebration overlay -->
	{#if showCelebration}
		<div class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
			<div class="text-center animate-bounce">
				<p class="text-6xl">🔥</p>
				<p class="mt-4 text-3xl font-black text-amber-400">{celebrationText}</p>
			</div>
		</div>
	{/if}
</div>
