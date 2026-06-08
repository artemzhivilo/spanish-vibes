<script lang="ts">
	import { answerQuizSet, nextQuizSetQuestion, completeQuiz } from '$lib/api/chat';
	import type { ActivityCard, ChatResponse } from '$lib/api/types';

	interface Props {
		card: ActivityCard;
		personaColor: string;
		onComplete: (reaction: ChatResponse | null) => void;
	}

	let { card, personaColor, onComplete }: Props = $props();

	// Current question state
	let question = $state<{ question: string; options: string[]; correct_index: number; is_retry: boolean } | null>(card.question ? {
		question: card.question,
		options: card.options ?? [],
		correct_index: 0,
		is_retry: false,
	} : null);
	let currentNum = $state(card.current ?? 1);
	let totalNum = $state(card.total ?? 0);
	let selected = $state<number | null>(null);
	let feedback = $state<{ correct: boolean; correct_answer: string; selected_answer: string } | null>(null);
	let submitting = $state(false);
	let loadingNext = $state(false);
	let isRetry = $state(false);
	let complete = $state(false);
	let finalScore = $state<{ correct: number; total: number } | null>(null);
	let completing = $state(false);

	async function selectOption(idx: number) {
		if (feedback || submitting) return;
		selected = idx;
		submitting = true;
		const res = await answerQuizSet(card.id, idx);
		feedback = {
			correct: res.correct,
			correct_answer: res.correct_answer,
			selected_answer: res.selected_answer,
		};
		isRetry = res.is_retry;
		submitting = false;

		if (!res.has_next) {
			// Load summary
			const next = await nextQuizSetQuestion(card.id);
			if (next.complete) {
				finalScore = { correct: next.correct_count ?? 0, total: next.total ?? 0 };
				complete = true;
			}
		}
	}

	async function loadNext() {
		loadingNext = true;
		const next = await nextQuizSetQuestion(card.id);
		if (next.complete) {
			finalScore = { correct: next.correct_count ?? 0, total: next.total ?? 0 };
			complete = true;
		} else if (next.question) {
			question = { ...next.question, is_retry: next.question.is_retry ?? false };
			currentNum = next.current ?? currentNum + 1;
			totalNum = next.total ?? totalNum;
			isRetry = next.is_retry ?? false;
			selected = null;
			feedback = null;
		}
		loadingNext = false;
	}

	async function handleComplete() {
		completing = true;
		const reaction = await completeQuiz(card.id);
		onComplete(reaction);
	}

	function optionStyle(idx: number): string {
		if (!feedback) {
			return 'background: #FBF7F0; color: #1a1410; border: 1px solid rgba(0,0,0,0.08);';
		}
		if (question && idx === question.correct_index) {
			return 'background: rgba(45,90,61,0.1); color: #2D5A3D; border: 1px solid rgba(45,90,61,0.2); font-weight: 700;';
		}
		if (idx === selected && !feedback.correct) {
			return 'background: rgba(200,85,61,0.1); color: #C8553D; border: 1px solid rgba(200,85,61,0.2); text-decoration: line-through;';
		}
		return 'background: #FBF7F0; color: rgba(60,45,30,0.4); border: 1px solid rgba(0,0,0,0.05);';
	}
</script>

<div class="rounded-2xl overflow-hidden" style="background: white; box-shadow: 0 1px 0 rgba(0,0,0,0.02), 0 4px 14px rgba(0,0,0,0.04);">
	<!-- Header -->
	<div class="px-4 py-3 flex items-center justify-between" style="border-bottom: 1px solid rgba(0,0,0,0.06);">
		<div class="flex items-center gap-2">
			<span class="text-[10px] uppercase tracking-widest font-bold" style="color: {personaColor};">Quiz</span>
			{#if card.topic}
				<span class="text-xs" style="color: rgba(60,45,30,0.55);">{card.topic}</span>
			{/if}
		</div>
		<span class="text-xs font-bold" style="color: rgba(60,45,30,0.45);">
			{currentNum}/{totalNum}
		</span>
	</div>

	<!-- Progress bar -->
	<div class="h-1" style="background: rgba(0,0,0,0.06);">
		<div class="h-full transition-all duration-300" style="background: {personaColor}; width: {(currentNum / totalNum) * 100}%;"></div>
	</div>

	{#if complete && finalScore}
		<!-- Summary -->
		<div class="px-4 py-5 text-center">
			<p class="text-3xl font-black" style="color: {personaColor};">
				{finalScore.correct}/{finalScore.total}
			</p>
			<p class="text-sm mt-1" style="color: rgba(60,45,30,0.55);">
				{finalScore.correct === finalScore.total ? 'Perfect!' : finalScore.correct >= finalScore.total * 0.7 ? 'Nice work!' : 'Keep practicing!'}
			</p>
		</div>
		<div class="px-4 py-3" style="border-top: 1px solid rgba(0,0,0,0.06);">
			<button
				class="w-full rounded-xl py-2.5 text-sm font-bold text-white transition active:scale-[0.98]"
				style="background: #C8553D;"
				onclick={handleComplete}
				disabled={completing}
			>
				{completing ? 'Loading...' : 'Continue'}
			</button>
		</div>
	{:else if question}
		<!-- Question -->
		<div class="px-4 py-3 space-y-3">
			{#if isRetry}
				<p class="text-[10px] uppercase tracking-widest font-bold" style="color: #C8553D;">Retry</p>
			{/if}
			<p class="text-[15px] font-semibold" style="color: #1a1410;">{question.question}</p>

			<div class="grid gap-2">
				{#each question.options as option, i}
					<button
						class="w-full text-left rounded-xl px-4 py-3 text-sm transition"
						style={optionStyle(i)}
						onclick={() => selectOption(i)}
						disabled={feedback !== null || submitting}
					>
						{option}
					</button>
				{/each}
			</div>

			{#if feedback && !complete}
				<button
					class="w-full rounded-xl py-2.5 text-sm font-bold text-white transition active:scale-[0.98]"
					style="background: #C8553D;"
					onclick={loadNext}
					disabled={loadingNext}
				>
					{loadingNext ? 'Loading...' : 'Next'}
				</button>
			{/if}
		</div>
	{/if}
</div>
