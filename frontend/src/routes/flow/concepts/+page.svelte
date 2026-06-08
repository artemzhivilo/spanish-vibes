<script lang="ts">
	import { onMount } from 'svelte';
	import { getConcepts } from '$lib/api/flow';
	import type { ConceptInfo } from '$lib/api/types';

	let concepts = $state<ConceptInfo[]>([]);
	let loading = $state(true);

	onMount(async () => {
		const res = await getConcepts();
		concepts = res.concepts;
		loading = false;
	});

	let grouped = $derived(() => {
		const tiers = new Map<number, ConceptInfo[]>();
		for (const c of concepts) {
			const list = tiers.get(c.difficulty_level) ?? [];
			list.push(c);
			tiers.set(c.difficulty_level, list);
		}
		return [...tiers.entries()].sort(([a], [b]) => a - b);
	});

	function tierName(level: number): string {
		return ['', 'Beginner', 'Elementary', 'Intermediate'][level] ?? `Tier ${level}`;
	}
</script>

<svelte:head>
	<title>Spanish Vibes - Concepts</title>
</svelte:head>

{#if loading}
	<div class="flex items-center justify-center py-20">
		<div class="h-8 w-8 animate-spin rounded-full border-4 border-t-transparent" style="border-color: rgba(200,85,61,0.2); border-top-color: transparent;"></div>
	</div>
{:else}
	<div class="space-y-6">
		<h2 class="text-2xl font-black" style="color: #1a1410; font-family: var(--font-serif);">Concepts</h2>

		{#each grouped() as [tier, tierConcepts]}
			<div>
				<h3 class="text-sm font-bold uppercase tracking-widest mb-3" style="color: rgba(60,45,30,0.45);">
					{tierName(tier)}
				</h3>
				<div class="grid gap-2">
					{#each tierConcepts as concept}
						<div class="rounded-2xl p-4 flex items-center justify-between" style="background: white; box-shadow: 0 1px 0 rgba(0,0,0,0.02), 0 4px 14px rgba(0,0,0,0.04);">
							<div class="flex-1 min-w-0">
								<div class="flex items-center gap-2">
									<span class="text-sm font-bold" style="color: #1a1410;">{concept.name}</span>
									{#if concept.is_mastered}
										<span class="rounded-full px-2 py-0.5 text-[10px] font-bold" style="background: rgba(45,90,61,0.1); color: #2D5A3D;">Mastered</span>
									{:else if concept.attempts > 0}
										<span class="rounded-full px-2 py-0.5 text-[10px] font-bold" style="background: rgba(200,85,61,0.1); color: #C8553D;">Learning</span>
									{:else if concept.teach_shown}
										<span class="rounded-full px-2 py-0.5 text-[10px] font-bold" style="background: rgba(0,0,0,0.05); color: rgba(60,45,30,0.55);">Seen</span>
									{/if}
								</div>
								<p class="text-xs mt-0.5 truncate" style="color: rgba(60,45,30,0.45);">{concept.description}</p>
							</div>
							<div class="flex items-center gap-3 ml-3">
								<div class="w-16 h-2 rounded-full overflow-hidden" style="background: rgba(0,0,0,0.06);">
									<div
										class="h-full rounded-full transition-all"
										style="width: {Math.round(concept.mastery * 100)}%; background: {concept.is_mastered ? '#2D5A3D' : concept.mastery > 0 ? '#C8553D' : 'rgba(0,0,0,0.08)'};"
									></div>
								</div>
								<span class="text-xs font-bold w-8 text-right" style="color: {concept.is_mastered ? '#2D5A3D' : concept.mastery > 0 ? '#C8553D' : 'rgba(60,45,30,0.35)'};">
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
