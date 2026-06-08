<script lang="ts">
	import { onMount } from 'svelte';
	import { getConcepts } from '$lib/api/flow';
	import type { ConceptInfo } from '$lib/api/types';
	import { Card } from '$lib/components/ui/card';
	import { Badge } from '$lib/components/ui/badge';

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
		<div class="h-8 w-8 animate-spin rounded-full border-4 border-emerald-500 border-t-transparent"></div>
	</div>
{:else}
	<div class="space-y-6">
		<h2 class="text-2xl font-black text-slate-50">Concepts</h2>

		{#each grouped() as [tier, tierConcepts]}
			<div>
				<h3 class="text-sm font-bold uppercase tracking-widest text-slate-400 mb-3">
					{tierName(tier)}
				</h3>
				<div class="grid gap-2">
					{#each tierConcepts as concept}
						<Card class="p-4 flex items-center justify-between">
							<div class="flex-1 min-w-0">
								<div class="flex items-center gap-2">
									<span class="text-sm font-bold text-slate-100">{concept.name}</span>
									{#if concept.is_mastered}
										<Badge color="emerald">Mastered</Badge>
									{:else if concept.attempts > 0}
										<Badge color="amber">Learning</Badge>
									{:else if concept.teach_shown}
										<Badge color="slate">Seen</Badge>
									{/if}
								</div>
								<p class="text-xs text-slate-500 mt-0.5 truncate">{concept.description}</p>
							</div>
							<div class="flex items-center gap-3 ml-3">
								<div class="w-16 h-2 rounded-full bg-[#0f1a1f] overflow-hidden">
									<div
										class="h-full rounded-full transition-all"
										class:bg-emerald-500={concept.is_mastered}
										class:bg-amber-500={!concept.is_mastered && concept.mastery > 0}
										class:bg-slate-700={concept.mastery === 0}
										style="width: {Math.round(concept.mastery * 100)}%"
									></div>
								</div>
								<span class="text-xs font-bold w-8 text-right"
									class:text-emerald-400={concept.is_mastered}
									class:text-amber-400={!concept.is_mastered && concept.mastery > 0}
									class:text-slate-600={concept.mastery === 0}
								>
									{Math.round(concept.mastery * 100)}%
								</span>
							</div>
						</Card>
					{/each}
				</div>
			</div>
		{/each}
	</div>
{/if}
