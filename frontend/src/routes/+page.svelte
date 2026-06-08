<script lang="ts">
	import { Button } from '$lib/components/ui/button';
	import { Card } from '$lib/components/ui/card';
	import { ProgressBar } from '$lib/components/ui/progress';
	import { Badge } from '$lib/components/ui/badge';

	let progress = $state<{
		xp: number;
		level: number;
		level_pct: number;
		streak: number;
		concepts_mastered: number;
		total_concepts: number;
	} | null>(null);
</script>

<svelte:head>
	<title>Spanish Vibes</title>
</svelte:head>

<div class="flex flex-col items-center justify-center min-h-[60vh] text-center px-4">
	<div class="mb-6">
		<span class="inline-flex h-20 w-20 items-center justify-center rounded-2xl bg-gradient-to-br from-emerald-400 to-emerald-600 text-4xl font-black text-white shadow-lg shadow-emerald-500/30">
			S
		</span>
	</div>

	<h2 class="text-3xl sm:text-4xl font-black text-slate-50 mb-3">Spanish Vibes</h2>
	<p class="text-lg text-slate-400 mb-8 max-w-md">
		Learn Spanish with AI conversations, flashcards, and spaced repetition.
	</p>

	{#if progress && progress.xp > 0}
		<Card class="w-full max-w-sm mb-8 p-5">
			<div class="flex items-center justify-between mb-3">
				<div class="flex items-center gap-2">
					<span class="inline-flex h-10 w-10 items-center justify-center rounded-full bg-emerald-500 text-lg font-black text-emerald-950 shadow-md">
						{progress.level}
					</span>
					<span class="text-xs uppercase tracking-widest text-slate-400 font-bold">Level</span>
				</div>
				{#if progress.streak > 0}
					<div class="flex items-center gap-1">
						<span class="text-xl">🔥</span>
						<span class="text-xl font-black text-amber-400">{progress.streak}</span>
					</div>
				{/if}
				<div class="text-right">
					<p class="text-lg font-black text-amber-400">{progress.xp} XP</p>
				</div>
			</div>
			<ProgressBar value={progress.level_pct} />
			<p class="mt-2 text-xs text-slate-500 text-center">
				{progress.concepts_mastered}/{progress.total_concepts} concepts mastered
			</p>
		</Card>

		<Button href="/flow" variant="gold" size="xl" class="w-full max-w-sm">
			Continue Learning
		</Button>
	{:else}
		<Button href="/flow" variant="primary" size="xl" class="w-full max-w-sm">
			Start Learning
		</Button>
	{/if}

	<div class="mt-6 flex flex-wrap justify-center gap-3">
		<Badge color="violet"><a href="/flow/concepts">Concepts</a></Badge>
		<Badge color="sky"><a href="/flow/stats">Stats</a></Badge>
		<Badge color="indigo"><a href="/flow/words">Words</a></Badge>
	</div>
</div>
