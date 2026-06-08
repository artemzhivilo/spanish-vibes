<script lang="ts">
	import type { ActivityCard } from '$lib/api/types';

	interface Props {
		card: ActivityCard;
		personaColor: string;
	}

	let { card, personaColor }: Props = $props();
</script>

<div class="rounded-2xl overflow-hidden" style="background: white; box-shadow: 0 1px 0 rgba(0,0,0,0.02), 0 4px 14px rgba(0,0,0,0.04);">
	<div class="px-4 py-3 flex items-center gap-2" style="border-bottom: 1px solid rgba(0,0,0,0.06);">
		<span class="text-[10px] uppercase tracking-widest font-bold" style="color: {personaColor};">Grammar</span>
		{#if card.title}
			<span class="text-sm font-bold" style="color: #1a1410;">{card.title}</span>
		{/if}
	</div>

	<div class="px-4 py-3 space-y-3">
		{#if card.explanation}
			<p class="text-sm leading-relaxed" style="color: rgba(60,45,30,0.8);">{card.explanation}</p>
		{/if}

		{#if card.examples?.length}
			<div class="space-y-2">
				{#each card.examples as ex}
					<div class="rounded-lg px-3 py-2" style="background: #FBF7F0;">
						<p class="text-sm font-semibold" style="color: {personaColor};">{ex.spanish}</p>
						<p class="text-xs" style="color: rgba(60,45,30,0.55);">{ex.english}</p>
					</div>
				{/each}
			</div>
		{/if}
	</div>
</div>
