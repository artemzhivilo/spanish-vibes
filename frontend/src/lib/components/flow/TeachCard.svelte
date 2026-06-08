<script lang="ts">
	import type { FlowCard } from '$lib/api/types';

	interface Props {
		card: FlowCard;
		conceptName: string;
		onContinue: () => void;
	}

	let { card, conceptName, onContinue }: Props = $props();
</script>

<div class="rounded-2xl overflow-hidden" style="background: white; box-shadow: 0 1px 0 rgba(0,0,0,0.02), 0 4px 14px rgba(0,0,0,0.04);">
	<div class="flex items-center gap-2 px-5 py-3" style="border-bottom: 1px solid rgba(0,0,0,0.06);">
		<span class="text-xs font-bold uppercase tracking-wider" style="color: #C8553D; font-family: var(--font-serif);">New Concept</span>
		<span class="text-xs font-bold" style="color: rgba(60,45,30,0.55);">{conceptName}</span>
	</div>

	<div class="px-5 py-4 lesson-prose leading-relaxed" style="color: rgba(60,45,30,0.7);">
		{@html card.teach_content}
	</div>

	<div class="px-5 pb-4">
		<button
			class="w-full rounded-xl py-3 text-center font-bold text-white transition active:scale-[0.98]"
			style="background: #C8553D;"
			onclick={onContinue}
		>
			Got it — Let's practice!
		</button>
	</div>
</div>
