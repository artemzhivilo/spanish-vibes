<script lang="ts">
	import { onMount } from 'svelte';
	import { getProgress } from '$lib/api/flow';

	let progress = $state<{
		xp: number;
		level: number;
		level_pct: number;
		streak: number;
	} | null>(null);
	let conceptsMastered = $state(0);
	let totalConcepts = $state(0);
	let loaded = $state(false);

	onMount(async () => {
		try {
			const res = await getProgress();
			progress = res.progress;
			conceptsMastered = res.concepts_mastered;
			totalConcepts = res.total_concepts;
		} catch {
		}
		loaded = true;
	});
</script>

<svelte:head>
	<title>Spanish Vibes</title>
</svelte:head>

<div class="flex flex-col items-center justify-center min-h-[60vh] text-center px-4">
	<div class="mb-6">
		<span class="inline-flex h-20 w-20 items-center justify-center rounded-2xl text-4xl font-black text-white" style="background: linear-gradient(135deg, #C8553D, #d4715c); box-shadow: 0 8px 24px rgba(200,85,61,0.25);">
			S
		</span>
	</div>

	<h2 class="text-3xl sm:text-4xl font-black mb-3" style="color: #1a1410; font-family: var(--font-serif);">Spanish Vibes</h2>
	<p class="text-lg mb-8 max-w-md" style="color: rgba(60,45,30,0.55);">
		Learn Spanish with AI conversations, flashcards, and spaced repetition.
	</p>

	{#if progress && progress.xp > 0}
		<div class="w-full max-w-sm mb-8 p-5 rounded-2xl" style="background: white; box-shadow: 0 1px 0 rgba(0,0,0,0.02), 0 4px 14px rgba(0,0,0,0.04);">
			<div class="flex items-center justify-between mb-3">
				<div class="flex items-center gap-2">
					<span class="inline-flex h-10 w-10 items-center justify-center rounded-full text-lg font-black text-white" style="background: #C8553D;">
						{progress.level}
					</span>
					<span class="text-xs uppercase tracking-widest font-bold" style="color: rgba(60,45,30,0.45);">Level</span>
				</div>
				{#if progress.streak > 0}
					<div class="flex items-center gap-1">
						<span class="text-xl">🔥</span>
						<span class="text-xl font-black" style="color: #C8553D;">{progress.streak}</span>
					</div>
				{/if}
				<div class="text-right">
					<p class="text-lg font-black" style="color: #C8553D;">{progress.xp} XP</p>
				</div>
			</div>
			<div class="h-2 rounded-full overflow-hidden" style="background: rgba(200,85,61,0.1);">
				<div class="h-full rounded-full transition-all" style="background: #C8553D; width: {progress.level_pct}%;"></div>
			</div>
			<p class="mt-2 text-xs text-center" style="color: rgba(60,45,30,0.45);">
				{conceptsMastered}/{totalConcepts} concepts mastered
			</p>
		</div>

		<a href="/flow" class="w-full max-w-sm inline-block rounded-xl py-3.5 text-center font-bold text-white text-lg transition active:scale-[0.98]" style="background: #C8553D;">
			Continue Learning
		</a>
	{:else}
		<a href="/flow" class="w-full max-w-sm inline-block rounded-xl py-3.5 text-center font-bold text-white text-lg transition active:scale-[0.98]" style="background: #C8553D;">
			Start Learning
		</a>
	{/if}

	<div class="mt-6 flex flex-wrap justify-center gap-3">
		<a href="/flow/concepts" class="rounded-full px-3 py-1 text-xs font-bold" style="background: rgba(200,85,61,0.1); color: #C8553D;">Concepts</a>
		<a href="/flow/stats" class="rounded-full px-3 py-1 text-xs font-bold" style="background: rgba(200,85,61,0.1); color: #C8553D;">Stats</a>
		<a href="/flow/words" class="rounded-full px-3 py-1 text-xs font-bold" style="background: rgba(200,85,61,0.1); color: #C8553D;">Words</a>
	</div>
</div>
