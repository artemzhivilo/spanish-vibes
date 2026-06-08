<script lang="ts">
	import { answerPlacement, nextPlacementQuestion, completeQuiz } from '$lib/api/chat';
	import type { ActivityCard, ChatResponse } from '$lib/api/types';

	interface Props {
		card: ActivityCard;
		personaColor: string;
		onComplete: (reaction: ChatResponse | null) => void;
	}

	let { card, personaColor, onComplete }: Props = $props();

	// Extract initial question from card (the card has a nested question object)
	let question = $state<{ question: string; options: string[] } | null>(
		(card as any).question ?? null
	);
	let currentNum = $state(card.current ?? 1);
	let totalNum = $state(card.total ?? 12);
	let selected = $state<number | null>(null);
	let feedback = $state<{ correct: boolean; correct_answer: string; selected_answer: string } | null>(null);
	let submitting = $state(false);
	let loadingNext = $state(false);
	let complete = $state(false);
	let result = $state<{ level: string; breakdown: any[]; gaps: string[] } | null>(null);
	let completing = $state(false);

	async function selectOption(idx: number) {
		if (feedback || submitting) return;
		selected = idx;
		submitting = true;
		const res = await answerPlacement(card.id, idx);
		feedback = { correct: res.correct, correct_answer: res.correct_answer, selected_answer: res.selected_answer };
		submitting = false;
	}

	async function loadNext() {
		loadingNext = true;
		const next = await nextPlacementQuestion(card.id);
		if (next.complete) {
			result = { level: next.level ?? '', breakdown: next.breakdown ?? [], gaps: next.gaps ?? [] };
			complete = true;
		} else if (next.question) {
			question = next.question;
			currentNum = next.current ?? currentNum + 1;
			totalNum = next.total ?? totalNum;
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
</script>

<div class="rounded-2xl overflow-hidden" style="background: white; box-shadow: 0 1px 0 rgba(0,0,0,0.02), 0 4px 14px rgba(0,0,0,0.04);">
	<div class="px-4 py-3 flex items-center justify-between" style="border-bottom: 1px solid rgba(0,0,0,0.06);">
		<span class="text-[10px] uppercase tracking-widest font-bold" style="color: {personaColor};">Placement Test</span>
		<span class="text-xs font-bold" style="color: rgba(60,45,30,0.45);">{currentNum}/{totalNum}</span>
	</div>

	<div class="h-1" style="background: rgba(0,0,0,0.06);">
		<div class="h-full transition-all duration-300" style="background: {personaColor}; width: {(currentNum / totalNum) * 100}%;"></div>
	</div>

	{#if complete && result}
		<div class="px-4 py-5 text-center space-y-3">
			<p class="text-3xl font-black" style="color: {personaColor};">{result.level}</p>
			<p class="text-sm" style="color: rgba(60,45,30,0.55);">Your estimated level</p>
			{#if result.breakdown.length}
				<div class="space-y-1">
					{#each result.breakdown as b}
						<div class="flex items-center justify-between text-xs px-2">
							<span style="color: #1a1410;">{b.label}</span>
							<span style="color: rgba(60,45,30,0.55);">{b.correct}/{b.total} ({b.pct}%)</span>
						</div>
					{/each}
				</div>
			{/if}
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
		<div class="px-4 py-3 space-y-3">
			<p class="text-[15px] font-semibold" style="color: #1a1410;">{question.question}</p>
			<div class="grid gap-2">
				{#each question.options as option, i}
					<button
						class="w-full text-left rounded-xl px-4 py-3 text-sm transition"
						style={feedback
							? (feedback.correct_answer === option
								? 'background: rgba(45,90,61,0.1); color: #2D5A3D; border: 1px solid rgba(45,90,61,0.2); font-weight: 700;'
								: selected === i
								? 'background: rgba(200,85,61,0.1); color: #C8553D; border: 1px solid rgba(200,85,61,0.2);'
								: 'background: #FBF7F0; color: rgba(60,45,30,0.4); border: 1px solid rgba(0,0,0,0.05);')
							: 'background: #FBF7F0; color: #1a1410; border: 1px solid rgba(0,0,0,0.08);'}
						onclick={() => selectOption(i)}
						disabled={feedback !== null || submitting}
					>
						{option}
					</button>
				{/each}
			</div>

			{#if feedback}
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
