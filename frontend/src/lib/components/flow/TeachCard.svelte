<script lang="ts">
	import type { FlowCard } from '$lib/api/types';

	interface Props {
		card: FlowCard;
		conceptName: string;
		onContinue: () => void;
	}

	let { card, conceptName, onContinue }: Props = $props();
</script>

<div class="rounded-2xl bg-[#1a2d35] shadow-lg shadow-black/20 overflow-hidden">
	<div class="flex items-center gap-2 px-5 py-3 bg-[#0f1a1f]">
		<span class="text-xs font-bold uppercase tracking-wider text-amber-400">New Concept</span>
		<span class="text-xs font-bold text-slate-400">{conceptName}</span>
	</div>

	<div class="px-5 py-4 lesson-prose text-slate-300 leading-relaxed">
		{@html card.teach_content}
	</div>

	<div class="px-5 pb-4">
		<button
			class="w-full rounded-xl bg-emerald-500 py-3 text-center font-black text-emerald-950 transition hover:bg-emerald-400 active:scale-[0.98]"
			onclick={onContinue}
		>
			Got it — Let's practice!
		</button>
	</div>
</div>
