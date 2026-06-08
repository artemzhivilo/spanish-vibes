<script lang="ts">
	import { onMount } from 'svelte';
	import { Button } from '$lib/components/ui/button';

	let loading = $state(true);
	let streak = $state(0);
	let conceptsMastered = $state(0);
	let totalConcepts = $state(0);
	let cardsAnswered = $state(0);
	let cefr = $state('A1');

	let cardHtml = $state('');

	onMount(async () => {
		// TODO: initialize flow session via API
		loading = false;
	});
</script>

<svelte:head>
	<title>Spanish Vibes - Flow</title>
</svelte:head>

<div class="flex flex-col items-center gap-3 max-w-[42rem] mx-auto">
	<!-- Compact flow header -->
	<div class="w-full flex items-center justify-between">
		<div class="flex items-center gap-3">
			<div class="flex items-center gap-1" title="Streak">
				<span class="text-lg" class:opacity-30={streak === 0}>🔥</span>
				<span class="text-base font-black text-amber-400">{streak}</span>
			</div>
			<span class="text-xs text-slate-500 font-bold">{conceptsMastered}/{totalConcepts}</span>
			<span class="hidden sm:inline rounded-full bg-amber-500/15 px-2 py-0.5 text-[10px] font-bold text-amber-300">
				{cefr}
			</span>
		</div>
		<div class="flex items-center gap-2">
			<span class="text-xs text-slate-500">{cardsAnswered} cards</span>
			<a
				href="/"
				class="rounded-full bg-slate-500/15 w-7 h-7 flex items-center justify-center text-xs font-bold text-slate-400 transition hover:bg-slate-500/25 hover:text-slate-200"
				title="Exit"
			>
				&times;
			</a>
		</div>
	</div>

	<!-- Card slot -->
	<div class="w-full">
		{#if loading}
			<div class="flex items-center justify-center py-20">
				<div class="h-8 w-8 animate-spin rounded-full border-4 border-emerald-500 border-t-transparent"></div>
			</div>
		{:else}
			<div class="rounded-2xl bg-[#1a2d35] p-6 shadow-lg shadow-black/20 text-center">
				<p class="text-slate-400 mb-4">Flow session ready</p>
				<p class="text-sm text-slate-500">Card rendering will be wired to the FastAPI backend</p>
			</div>
		{/if}
	</div>

	<!-- Celebration overlay -->
	<div id="celebration-overlay" class="fixed inset-0 z-50 hidden items-center justify-center bg-black/60 backdrop-blur-sm">
		<div class="text-center animate-bounce">
			<p class="text-6xl">🔥</p>
			<p class="mt-4 text-3xl font-black text-amber-400"></p>
		</div>
	</div>
</div>
