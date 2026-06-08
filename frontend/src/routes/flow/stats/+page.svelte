<script lang="ts">
	import { onMount } from 'svelte';
	import { getStats } from '$lib/api/flow';
	import type { StatsResponse, TierStats } from '$lib/api/types';

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
		<div class="h-8 w-8 animate-spin rounded-full border-4 border-t-transparent" style="border-color: rgba(200,85,61,0.2); border-top-color: transparent;"></div>
	</div>
{:else if data}
	<div class="space-y-6">
		<h2 class="text-2xl font-black" style="color: #1a1410; font-family: var(--font-serif);">Your Stats</h2>

		<div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
			{#each [
				{ value: data.progress?.xp ?? 0, label: 'Total XP' },
				{ value: data.progress?.level ?? 1, label: 'Level' },
				{ value: data.progress?.streak ?? 0, label: 'Streak' },
				{ value: data.cefr, label: 'CEFR' },
			] as stat}
				<div class="rounded-2xl p-4 text-center" style="background: white; box-shadow: 0 1px 0 rgba(0,0,0,0.02), 0 4px 14px rgba(0,0,0,0.04);">
					<p class="text-2xl font-black" style="color: #C8553D;">{stat.value}</p>
					<p class="text-[10px] uppercase tracking-widest font-bold" style="color: rgba(60,45,30,0.45);">{stat.label}</p>
				</div>
			{/each}
		</div>

		<div class="rounded-2xl p-5" style="background: white; box-shadow: 0 1px 0 rgba(0,0,0,0.02), 0 4px 14px rgba(0,0,0,0.04);">
			<div class="flex items-center justify-between mb-3">
				<h3 class="text-lg font-bold" style="color: #1a1410;">Concepts Mastered</h3>
				<span class="text-sm font-bold" style="color: #2D5A3D;">{data.concepts_mastered}/{data.total_concepts}</span>
			</div>
			<div class="h-2 rounded-full overflow-hidden" style="background: rgba(200,85,61,0.1);">
				<div class="h-full rounded-full" style="background: #C8553D; width: {data.total_concepts ? (data.concepts_mastered / data.total_concepts * 100) : 0}%;"></div>
			</div>
		</div>

		{#each Object.entries(data.tiers) as [tier, stats]}
			<div class="rounded-2xl p-5" style="background: white; box-shadow: 0 1px 0 rgba(0,0,0,0.02), 0 4px 14px rgba(0,0,0,0.04);">
				<div class="flex items-center justify-between mb-3">
					<h3 class="text-base font-bold" style="color: #1a1410;">{tierLabel(tier)}</h3>
					<span class="text-xs font-bold" style="color: rgba(60,45,30,0.55);">{stats.mastered}/{stats.total} mastered</span>
				</div>
				<div class="h-2 rounded-full overflow-hidden mb-3" style="background: rgba(200,85,61,0.1);">
					<div class="h-full rounded-full" style="background: #C8553D; width: {stats.total ? (stats.mastered / stats.total * 100) : 0}%;"></div>
				</div>
				<div class="grid gap-1.5">
					{#each stats.concepts as concept}
						<div class="flex items-center justify-between py-1.5 px-3 rounded-lg" style="background: #FBF7F0;">
							<span class="text-sm font-medium" style="color: #1a1410;">{concept.name}</span>
							<div class="flex items-center gap-2">
								<div class="w-16 h-1.5 rounded-full overflow-hidden" style="background: rgba(0,0,0,0.06);">
									<div
										class="h-full rounded-full transition-all duration-300"
										style="width: {Math.round(concept.mastery * 100)}%; background: {concept.is_mastered ? '#2D5A3D' : concept.mastery > 0 ? '#C8553D' : 'rgba(0,0,0,0.1)'};"
									></div>
								</div>
								<span class="text-[10px] font-bold w-8 text-right" style="color: {concept.is_mastered ? '#2D5A3D' : concept.mastery > 0 ? '#C8553D' : 'rgba(60,45,30,0.35)'};">
									{Math.round(concept.mastery * 100)}%
								</span>
							</div>
						</div>
					{/each}
				</div>
			</div>
		{/each}
	</div>
{/if}
