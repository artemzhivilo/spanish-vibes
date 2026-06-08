<script lang="ts">
	import { onMount } from 'svelte';
	import { getLearnerStats } from '$lib/api/chat';

	interface WordEntry {
		word: string;
		translation: string;
		domain: string | null;
		repetitions: number;
		times_correct: number;
		times_wrong: number;
	}

	let words = $state<WordEntry[]>([]);
	let loading = $state(true);
	let search = $state('');

	onMount(async () => {
		try {
			const stats = await getLearnerStats();
			words = stats.words;
		} catch (e) {
			console.error('Failed to load words:', e);
		}
		loading = false;
	});

	let filtered = $derived(
		search
			? words.filter(
					w =>
						w.word.toLowerCase().includes(search.toLowerCase()) ||
						w.translation.toLowerCase().includes(search.toLowerCase())
				)
			: words
	);

	function wordStatus(w: WordEntry): string {
		if (w.repetitions >= 3 && w.times_correct > w.times_wrong) return 'mastered';
		if (w.repetitions > 0) return 'learning';
		return 'new';
	}
</script>

<svelte:head>
	<title>Spanish Vibes - Words</title>
</svelte:head>

{#if loading}
	<div class="flex items-center justify-center py-20">
		<div class="h-8 w-8 animate-spin rounded-full border-4 border-t-transparent" style="border-color: rgba(200,85,61,0.2); border-top-color: transparent;"></div>
	</div>
{:else}
	<div class="space-y-4">
		<div class="flex items-center justify-between">
			<h2 class="text-2xl font-black" style="color: #1a1410; font-family: var(--font-serif);">Vocabulary</h2>
			<span class="text-sm font-bold" style="color: rgba(60,45,30,0.55);">{words.length} words</span>
		</div>

		<input
			type="text"
			placeholder="Search words..."
			bind:value={search}
			class="w-full rounded-xl px-4 py-2.5 text-sm outline-none transition"
			style="background: white; border: 1px solid rgba(0,0,0,0.08); color: #1a1410;"
		/>

		<div class="grid gap-2">
			{#each filtered as word}
				{@const status = wordStatus(word)}
				<div class="rounded-2xl p-3 flex items-center justify-between" style="background: white; box-shadow: 0 1px 0 rgba(0,0,0,0.02), 0 4px 14px rgba(0,0,0,0.04);">
					<div>
						<span class="text-sm font-bold" style="color: #C8553D;">{word.word}</span>
						<span class="text-sm mx-1.5" style="color: rgba(60,45,30,0.35);">&rarr;</span>
						<span class="text-sm" style="color: #1a1410;">{word.translation}</span>
						{#if word.domain}
							<span class="text-[10px] ml-2" style="color: rgba(60,45,30,0.4);">{word.domain}</span>
						{/if}
					</div>
					<div class="flex items-center gap-2">
						{#if word.times_correct + word.times_wrong > 0}
							<span class="text-[10px] font-bold" style="color: rgba(60,45,30,0.45);">
								{word.times_correct}/{word.times_correct + word.times_wrong}
							</span>
						{/if}
						{#if status === 'mastered'}
							<span class="rounded-full px-2 py-0.5 text-[10px] font-bold" style="background: rgba(45,90,61,0.1); color: #2D5A3D;">Mastered</span>
						{:else if status === 'learning'}
							<span class="rounded-full px-2 py-0.5 text-[10px] font-bold" style="background: rgba(200,85,61,0.1); color: #C8553D;">Learning</span>
						{:else}
							<span class="rounded-full px-2 py-0.5 text-[10px] font-bold" style="background: rgba(0,0,0,0.05); color: rgba(60,45,30,0.55);">New</span>
						{/if}
					</div>
				</div>
			{:else}
				<p class="text-center py-8" style="color: rgba(60,45,30,0.45);">
					{search ? 'No words match your search' : 'No words tracked yet. Start chatting to build your vocabulary!'}
				</p>
			{/each}
		</div>
	</div>
{/if}
