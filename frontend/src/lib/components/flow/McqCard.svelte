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

	function optionClass(option: string): string {
		if (result === null) {
			return selected === option
				? 'border-emerald-500 bg-[#162028] text-slate-50'
				: 'border-[#1e3a47] bg-[#0f1a1f] text-slate-300 hover:border-emerald-500 hover:text-slate-50 hover:bg-[#162028] cursor-pointer';
		}
		if (option === result.correct_answer) {
			return 'border-emerald-500 bg-emerald-500/10 text-emerald-300';
		}
		if (option === selected && !result.is_correct) {
			return 'border-red-500 bg-red-500/10 text-red-300';
		}
		return 'border-[#1e3a47] bg-[#0f1a1f] text-slate-500 opacity-40';
	}
</script>

<div class={cn('rounded-2xl bg-[#1a2d35] shadow-lg shadow-black/20 overflow-hidden', animClass)}>
	<!-- Header -->
	<div class="flex items-center gap-2 px-5 py-3 bg-[#0f1a1f]">
		<span class="text-xs font-bold uppercase tracking-wider text-emerald-400">{conceptName}</span>
		{#if card.difficulty > 1}
			<span class="text-[10px] font-bold text-amber-400/60">Lv{card.difficulty}</span>
		{/if}
	</div>

	<!-- Question -->
	<div class="px-5 pt-4 pb-2">
		<p class="text-lg font-semibold text-slate-100 leading-relaxed">{card.question}</p>
		{#if card.english_prompt}
			<p class="mt-1 text-sm text-slate-400">{card.english_prompt}</p>
		{/if}
	</div>

	<!-- Options -->
	<div class="px-5 pb-4 grid gap-2.5">
		{#each card.options as option}
			<button
				class={cn(
					'w-full text-left px-4 py-3 rounded-xl border-2 font-semibold text-[0.95rem] transition-all duration-150',
					optionClass(option),
				)}
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
			<div class={cn(
				'rounded-xl p-3 text-sm font-semibold',
				result.is_correct
					? 'bg-emerald-500/10 border border-emerald-500/25 text-emerald-300'
					: 'bg-red-500/10 border border-red-500/20 text-red-300'
			)}>
				{#if result.is_correct}
					Correct! +{result.xp_earned} XP
				{:else}
					<p>The answer is <strong class="text-slate-100">{result.correct_answer}</strong></p>
				{/if}
			</div>

			<button
				class="mt-3 w-full rounded-xl bg-emerald-500 py-3 text-center font-black text-emerald-950 transition hover:bg-emerald-400 active:scale-[0.98]"
				onclick={onNext}
			>
				Continue
			</button>
		</div>
	{/if}
</div>
