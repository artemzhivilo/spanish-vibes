<script lang="ts">
	import type { ActivityCard } from '$lib/api/types';

	interface Props {
		card: ActivityCard;
		personaColor: string;
	}

	let { card, personaColor }: Props = $props();

	let currentIdx = $state(0);
	let flipped = $state(false);
	let cards = $derived(card.cards ?? []);
	let current = $derived(cards[currentIdx]);

	function flip() {
		flipped = !flipped;
	}

	function next() {
		if (currentIdx < cards.length - 1) {
			currentIdx++;
			flipped = false;
		}
	}

	function prev() {
		if (currentIdx > 0) {
			currentIdx--;
			flipped = false;
		}
	}
</script>

<div class="rounded-2xl overflow-hidden" style="background: white; box-shadow: 0 1px 0 rgba(0,0,0,0.02), 0 4px 14px rgba(0,0,0,0.04);">
	{#if card.intro}
		<div class="px-4 py-3" style="border-bottom: 1px solid rgba(0,0,0,0.06);">
			<p class="text-sm italic" style="color: rgba(60,45,30,0.7);">{card.intro}</p>
		</div>
	{/if}

	{#if current}
		<div class="px-4 py-5">
			<button
				class="w-full text-center py-6 rounded-xl transition active:scale-[0.98] cursor-pointer"
				style="background: #FBF7F0; border: 1px solid rgba(0,0,0,0.06);"
				onclick={flip}
			>
				{#if flipped}
					<p class="text-lg" style="color: rgba(60,45,30,0.7);">{current.back}</p>
					{#if current.example}
						<p class="text-xs mt-2 italic" style="color: rgba(60,45,30,0.45);">{current.example}</p>
					{/if}
				{:else}
					<p class="text-xl font-bold" style="color: {personaColor};">{current.front}</p>
					<p class="text-[10px] mt-2 uppercase tracking-widest" style="color: rgba(60,45,30,0.35);">Tap to flip</p>
				{/if}
			</button>

			<div class="flex items-center justify-between mt-3">
				<button
					class="rounded-lg px-3 py-1.5 text-xs font-bold transition"
					style="background: rgba(0,0,0,0.05); color: {currentIdx > 0 ? '#1a1410' : 'rgba(60,45,30,0.3)'};"
					onclick={prev}
					disabled={currentIdx === 0}
				>
					Previous
				</button>
				<span class="text-xs font-bold" style="color: rgba(60,45,30,0.45);">
					{currentIdx + 1}/{cards.length}
				</span>
				<button
					class="rounded-lg px-3 py-1.5 text-xs font-bold transition"
					style="background: rgba(0,0,0,0.05); color: {currentIdx < cards.length - 1 ? '#1a1410' : 'rgba(60,45,30,0.3)'};"
					onclick={next}
					disabled={currentIdx === cards.length - 1}
				>
					Next
				</button>
			</div>
		</div>
	{/if}
</div>
