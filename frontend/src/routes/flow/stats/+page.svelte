<script lang="ts">
	import { onMount } from 'svelte';
	import { getStats } from '$lib/api/flow';
	import type { StatsResponse, TierStats } from '$lib/api/types';
	import { Card } from '$lib/components/ui/card';
	import { ProgressBar } from '$lib/components/ui/progress';

	let data = $state<StatsResponse | null>(null);
	let loading = $state(true);

	onMount(async () => {
		data = await getStats();
		loading = false;
	});

	function tierLabel(tier: string): string {
		const labels: Record<string, string> = {
			'1': 'Beginner',
			'2': 'Elementary',
			'3': 'Intermediate',
		};
		return labels[tier] ?? `Tier ${tier}`;
	}
</script>

<svelte:head>
	<title>Spanish Vibes - Stats</title>
</svelte:head>

{#if loading}
	<div class="flex items-center justify-center py-20">
		<div class="h-8 w-8 animate-spin rounded-full border-4 border-emerald-500 border-t-transparent"></div>
	</div>
{:else if data}
	<div class="space-y-6">
		<h2 class="text-2xl font-black text-slate-50">Your Stats</h2>

		<!-- Overview -->
		<div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
			<Card class="p-4 text-center">
				<p class="text-2xl font-black text-amber-400">{data.progress?.xp ?? 0}</p>
				<p class="text-[10px] uppercase tracking-widest text-slate-500 font-bold">Total XP</p>
			</Card>
			<Card class="p-4 text-center">
				<p class="text-2xl font-black text-emerald-400">{data.progress?.level ?? 1}</p>
				<p class="text-[10px] uppercase tracking-widest text-slate-500 font-bold">Level</p>
			</Card>
			<Card class="p-4 text-center">
				<p class="text-2xl font-black text-amber-400">{data.progress?.streak ?? 0}</p>
				<p class="text-[10px] uppercase tracking-widest text-slate-500 font-bold">Streak</p>
			</Card>
			<Card class="p-4 text-center">
				<p class="text-2xl font-black text-sky-400">{data.cefr}</p>
				<p class="text-[10px] uppercase tracking-widest text-slate-500 font-bold">CEFR</p>
			</Card>
		</div>

		<!-- Mastery overview -->
		<Card class="p-5">
			<div class="flex items-center justify-between mb-3">
				<h3 class="text-lg font-bold text-slate-100">Concepts Mastered</h3>
				<span class="text-sm font-bold text-emerald-400">{data.concepts_mastered}/{data.total_concepts}</span>
			</div>
			<ProgressBar value={data.concepts_mastered} max={data.total_concepts} />
		</Card>

		<!-- Tier breakdown -->
		{#each Object.entries(data.tiers) as [tier, stats]}
			<Card class="p-5">
				<div class="flex items-center justify-between mb-3">
					<h3 class="text-base font-bold text-slate-100">{tierLabel(tier)}</h3>
					<span class="text-xs font-bold text-slate-400">{stats.mastered}/{stats.total} mastered</span>
				</div>
				<ProgressBar value={stats.mastered} max={stats.total} class="mb-3" />
				<div class="grid gap-1.5">
					{#each stats.concepts as concept}
						<div class="flex items-center justify-between py-1.5 px-3 rounded-lg bg-[#0f1a1f]">
							<span class="text-sm font-medium text-slate-300">{concept.name}</span>
							<div class="flex items-center gap-2">
								<div class="w-16 h-1.5 rounded-full bg-[#1e3a47] overflow-hidden">
									<div
										class="h-full rounded-full transition-all duration-300"
										class:bg-emerald-500={concept.is_mastered}
										class:bg-amber-500={!concept.is_mastered && concept.mastery > 0}
										class:bg-slate-600={concept.mastery === 0}
										style="width: {Math.round(concept.mastery * 100)}%"
									></div>
								</div>
								<span class="text-[10px] font-bold w-8 text-right"
									class:text-emerald-400={concept.is_mastered}
									class:text-amber-400={!concept.is_mastered && concept.mastery > 0}
									class:text-slate-500={concept.mastery === 0}
								>
									{Math.round(concept.mastery * 100)}%
								</span>
							</div>
						</div>
					{/each}
				</div>
			</Card>
		{/each}
	</div>
{/if}
