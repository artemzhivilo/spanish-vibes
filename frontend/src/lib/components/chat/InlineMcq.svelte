<script lang="ts">
	import { answerMcq, completeQuiz } from '$lib/api/chat';
	import type { ActivityCard, ChatResponse } from '$lib/api/types';

	interface Props {
		card: ActivityCard;
		personaColor: string;
		onComplete: (reaction: ChatResponse | null) => void;
	}

	let { card, personaColor, onComplete }: Props = $props();

	let selected = $state<number | null>(null);
	let feedback = $state<{ correct: boolean; explanation: string; correct_index: number } | null>(null);
	let submitting = $state(false);
	let completing = $state(false);

	async function selectOption(idx: number) {
		if (feedback || submitting) return;
		selected = idx;
		submitting = true;
		const res = await answerMcq(card.id, idx);
		feedback = { correct: res.correct, explanation: res.explanation, correct_index: res.correct_index };
		submitting = false;
	}

	async function handleComplete() {
		completing = true;
		const reaction = await completeQuiz(card.id);
		onComplete(reaction);
	}

	function optionStyle(idx: number): string {
		if (!feedback) {
			return selected === idx
				? `background: ${personaColor}; color: white; border: 1px solid transparent;`
				: 'background: #FBF7F0; color: #1a1410; border: 1px solid rgba(0,0,0,0.08);';
		}
		if (idx === feedback.correct_index) {
			return 'background: rgba(45,90,61,0.1); color: #2D5A3D; border: 1px solid rgba(45,90,61,0.2); font-weight: 700;';
		}
		if (idx === selected && !feedback.correct) {
			return 'background: rgba(200,85,61,0.1); color: #C8553D; border: 1px solid rgba(200,85,61,0.2); text-decoration: line-through;';
		}
		return 'background: #FBF7F0; color: rgba(60,45,30,0.4); border: 1px solid rgba(0,0,0,0.05);';
	}
</script>

<div class="rounded-2xl overflow-hidden" style="background: white; box-shadow: 0 1px 0 rgba(0,0,0,0.02), 0 4px 14px rgba(0,0,0,0.04);">
	{#if card.intro}
		<div class="px-4 py-3" style="border-bottom: 1px solid rgba(0,0,0,0.06);">
			<p class="text-sm italic" style="color: rgba(60,45,30,0.7);">{card.intro}</p>
		</div>
	{/if}

	<div class="px-4 py-3 space-y-3">
		{#if card.question}
			<p class="text-[15px] font-semibold" style="color: #1a1410;">{card.question}</p>
		{/if}

		<div class="grid gap-2">
			{#each card.options ?? [] as option, i}
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

		{#if feedback}
			<div class="rounded-xl px-3 py-2.5" style="background: {feedback.correct ? 'rgba(45,90,61,0.08)' : 'rgba(200,85,61,0.08)'};">
				<p class="text-sm font-bold" style="color: {feedback.correct ? '#2D5A3D' : '#C8553D'};">
					{feedback.correct ? 'Correct!' : 'Not quite'}
				</p>
				<p class="text-xs mt-0.5" style="color: rgba(60,45,30,0.7);">{feedback.explanation}</p>
			</div>
		{/if}
	</div>

	{#if feedback}
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
	{/if}
</div>
