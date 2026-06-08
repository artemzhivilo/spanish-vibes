<script lang="ts">
	import { onMount } from 'svelte';
	import { getWords } from '$lib/api/flow';
	import type { WordInfo } from '$lib/api/types';
	import { Card } from '$lib/components/ui/card';
	import { Badge } from '$lib/components/ui/badge';

	let words = $state<WordInfo[]>([]);
	let loading = $state(true);
	let search = $state('');

	onMount(async () => {
		const res = await getWords();
		words = res.words;
		loading = false;
	});

	let filtered = $derived(
		search
			? words.filter(
					w =>
						w.spanish.toLowerCase().includes(search.toLowerCase()) ||
						w.english.toLowerCase().includes(search.toLowerCase())
				)
			: words
	);
</script>

<svelte:head>
	<title>Spanish Vibes - Words</title>
</svelte:head>

{#if loading}
	<div class="flex items-center justify-center py-20">
		<div class="h-8 w-8 animate-spin rounded-full border-4 border-emerald-500 border-t-transparent"></div>
	</div>
{:else}
	<div class="space-y-4">
		<div class="flex items-center justify-between">
			<h2 class="text-2xl font-black text-slate-50">Vocabulary</h2>
			<span class="text-sm text-slate-400 font-bold">{words.length} words</span>
		</div>

		<!-- Search -->
		<input
			type="text"
			placeholder="Search words..."
			bind:value={search}
			class="w-full rounded-xl bg-[#0f1a1f] border-2 border-[#1e3a47] px-4 py-2.5 text-sm text-slate-100 placeholder-slate-500 outline-none focus:border-emerald-500 transition"
		/>

		<!-- Word list -->
		<div class="grid gap-2">
			{#each filtered as word}
				<Card class="p-3 flex items-center justify-between">
					<div class="flex items-center gap-3">
						{#if word.emoji}
							<span class="text-xl">{word.emoji}</span>
						{/if}
						<div>
							<span class="text-sm font-bold text-amber-400">{word.spanish}</span>
							<span class="text-sm text-slate-400 mx-1.5">&rarr;</span>
							<span class="text-sm text-slate-300">{word.english}</span>
						</div>
					</div>
					<div class="flex items-center gap-2">
						{#if word.times_seen > 0}
							<span class="text-[10px] font-bold text-slate-500">
								{word.times_correct}/{word.times_seen}
							</span>
						{/if}
						{#if word.status === 'mastered'}
							<Badge color="emerald">Mastered</Badge>
						{:else if word.status === 'learning'}
							<Badge color="amber">Learning</Badge>
						{:else}
							<Badge color="slate">New</Badge>
						{/if}
					</div>
				</Card>
			{:else}
				<p class="text-center text-slate-500 py-8">
					{search ? 'No words match your search' : 'No words tracked yet'}
				</p>
			{/each}
		</div>
	</div>
{/if}
