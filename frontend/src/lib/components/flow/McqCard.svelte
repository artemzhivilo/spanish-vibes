<script lang="ts">
	import type { FlowCard, AnswerResponse } from '$lib/api/types';
	import { cn } from '$lib/utils/cn';

	interface Props {
		card: FlowCard;
		conceptName: string;
		onAnswer: (chosenOption: string) => Promise<AnswerResponse>;
		onNext: () => void;
	}

	let { card, conceptName, onAnswer, onNext }: Props = $props();

	let selected = $state<string | null>(null);
	let result = $state<AnswerResponse | null>(null);
	let answering = $state(false);
	let animClass = $state('');

	async function handleSelect(option: string) {
		if (selected !== null || answering) return;
		answering = true;
		selected = option;

		const res = await onAnswer(option);
		result = res;
		animClass = res.is_correct ? 'correct-pop' : 'wrong-shake';
		answering = false;
	}

	function optionStyle(option: string): string {
		if (result === null) {
			return selected === option
				? 'border-color: #C8553D; background: rgba(200,85,61,0.05); color: #1a1410;'
				: 'border-color: rgba(0,0,0,0.08); background: white; color: #1a1410;';
		}
		if (option === result.correct_answer) {
			return 'border-color: #2D5A3D; background: rgba(45,90,61,0.08); color: #2D5A3D;';
		}
		if (option === selected && !result.is_correct) {
			return 'border-color: #C8553D; background: rgba(200,85,61,0.08); color: #C8553D;';
		}
		return 'border-color: rgba(0,0,0,0.04); background: rgba(0,0,0,0.02); color: rgba(60,45,30,0.35);';
	}
</script>

<div class={cn('rounded-2xl overflow-hidden', animClass)} style="background: white; box-shadow: 0 1px 0 rgba(0,0,0,0.02), 0 4px 14px rgba(0,0,0,0.04);">
	<!-- Header -->
	<div class="flex items-center gap-2 px-5 py-3" style="border-bottom: 1px solid rgba(0,0,0,0.06);">
		<span class="text-xs font-bold uppercase tracking-wider" style="color: #C8553D; font-family: var(--font-serif);">{conceptName}</span>
		{#if card.difficulty > 1}
			<span class="text-[10px] font-bold" style="color: rgba(60,45,30,0.45);">Lv{card.difficulty}</span>
		{/if}
	</div>

	<!-- Question -->
	<div class="px-5 pt-4 pb-2">
		<p class="text-lg font-semibold leading-relaxed" style="color: #1a1410;">{card.question}</p>
		{#if card.english_prompt}
			<p class="mt-1 text-sm" style="color: rgba(60,45,30,0.55);">{card.english_prompt}</p>
		{/if}
	</div>

	<!-- Options -->
	<div class="px-5 pb-4 grid gap-2.5">
		{#each card.options as option}
			<button
				class="w-full text-left px-4 py-3 rounded-xl border-2 font-semibold text-[0.95rem] transition-all duration-150"
				class:cursor-pointer={result === null}
				style={optionStyle(option)}
				disabled={result !== null}
				onclick={() => handleSelect(option)}
			>
				{option}
			</button>
		{/each}
	</div>

	<!-- Feedback -->
	{#if result}
		<div class="px-5 pb-4">
			<div
				class="rounded-xl p-3 text-sm font-semibold"
				style={result.is_correct
					? 'background: rgba(45,90,61,0.08); border: 1px solid rgba(45,90,61,0.15); color: #2D5A3D;'
					: 'background: rgba(200,85,61,0.08); border: 1px solid rgba(200,85,61,0.15); color: #C8553D;'}
			>
				{#if result.is_correct}
					Correct! +{result.xp_earned} XP
				{:else}
					<p>The answer is <strong style="color: #1a1410;">{result.correct_answer}</strong></p>
				{/if}
			</div>

			<button
				class="mt-3 w-full rounded-xl py-3 text-center font-bold text-white transition active:scale-[0.98]"
				style="background: #C8553D;"
				onclick={onNext}
			>
				Continue
			</button>
		</div>
	{/if}
</div>
