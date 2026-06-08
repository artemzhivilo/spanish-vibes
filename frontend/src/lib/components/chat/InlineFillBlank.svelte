<script lang="ts">
	import { answerFillBlank, completeQuiz } from '$lib/api/chat';
	import type { ActivityCard, ChatResponse } from '$lib/api/types';

	interface Props {
		card: ActivityCard;
		personaColor: string;
		onComplete: (reaction: ChatResponse | null) => void;
	}

	let { card, personaColor, onComplete }: Props = $props();

	let answers = $state<Record<number, string>>({});
	let feedback = $state<Record<number, { correct: boolean; correct_answer: string }>>({});
	let submitting = $state<number | null>(null);
	let allDone = $state(false);
	let completing = $state(false);

	async function submitBlank(idx: number) {
		const answer = answers[idx]?.trim();
		if (!answer || submitting !== null) return;
		submitting = idx;
		const res = await answerFillBlank(card.id, idx, answer);
		feedback[idx] = { correct: res.correct, correct_answer: res.correct_answer };
		submitting = null;
		if (res.last) {
			allDone = true;
		}
	}

	async function handleComplete() {
		completing = true;
		const reaction = await completeQuiz(card.id);
		onComplete(reaction);
	}

	function handleKeydown(e: KeyboardEvent, idx: number) {
		if (e.key === 'Enter') {
			e.preventDefault();
			submitBlank(idx);
		}
	}
</script>

<div class="rounded-2xl overflow-hidden" style="background: white; box-shadow: 0 1px 0 rgba(0,0,0,0.02), 0 4px 14px rgba(0,0,0,0.04);">
	{#if card.intro}
		<div class="px-4 py-3" style="border-bottom: 1px solid rgba(0,0,0,0.06);">
			<p class="text-sm italic" style="color: rgba(60,45,30,0.7);">{card.intro}</p>
		</div>
	{/if}

	<div class="px-4 py-3 space-y-3">
		{#each card.sentences ?? [] as sentence, i}
			<div class="space-y-1.5">
				<p class="text-[15px]" style="color: #1a1410;">
					{sentence.text_with_blank}
				</p>
				{#if feedback[i]}
					<div class="flex items-center gap-2">
						{#if feedback[i].correct}
							<span class="text-sm font-bold" style="color: #2D5A3D;">
								{feedback[i].correct_answer}
							</span>
						{:else}
							<span class="text-sm line-through" style="color: #C8553D;">{answers[i]}</span>
							<span style="color: rgba(60,45,30,0.4);" class="text-sm">&rarr;</span>
							<span class="text-sm font-bold" style="color: #2D5A3D;">{feedback[i].correct_answer}</span>
						{/if}
					</div>
				{:else}
					<div class="flex gap-2">
						<input
							type="text"
							bind:value={answers[i]}
							onkeydown={(e) => handleKeydown(e, i)}
							placeholder={sentence.hint || 'Your answer...'}
							disabled={submitting !== null}
							class="flex-1 rounded-lg px-3 py-2 text-sm outline-none"
							style="background: #FBF7F0; border: 1px solid rgba(0,0,0,0.08); color: #1a1410;"
						/>
						<button
							onclick={() => submitBlank(i)}
							disabled={!answers[i]?.trim() || submitting !== null}
							class="rounded-lg px-3 py-2 text-sm font-bold text-white transition active:scale-95 disabled:opacity-40"
							style="background: {personaColor};"
						>
							Check
						</button>
					</div>
				{/if}
			</div>
		{/each}
	</div>

	{#if allDone}
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
