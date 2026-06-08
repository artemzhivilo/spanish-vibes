<script lang="ts">
	import { api } from '$lib/api/client';
	import { Card } from '$lib/components/ui/card';
	import { Button } from '$lib/components/ui/button';

	let resetting = $state(false);
	let resetDone = $state(false);
	let confirmReset = $state(false);

	async function handleReset() {
		if (!confirmReset) {
			confirmReset = true;
			return;
		}
		resetting = true;
		await api.post('/dev/reset-progress', {});
		resetting = false;
		resetDone = true;
		confirmReset = false;
	}

	function cancelReset() {
		confirmReset = false;
	}
</script>

<svelte:head>
	<title>Spanish Vibes - Settings</title>
</svelte:head>

<div class="flex flex-col gap-4 max-w-[42rem] mx-auto">
	<h2 class="text-xl font-black text-slate-50">Settings</h2>

	<Card class="p-5">
		<h3 class="text-sm font-bold text-slate-300 mb-1">Reset Progress</h3>
		<p class="text-xs text-slate-500 mb-4">
			Clear all learning data — XP, streaks, concept mastery, conversation history. Starts you fresh from scratch.
		</p>

		{#if resetDone}
			<div class="rounded-xl bg-emerald-500/15 px-4 py-3 text-sm text-emerald-300 font-bold">
				Progress reset! <a href="/flow" class="underline">Start fresh</a>
			</div>
		{:else if confirmReset}
			<div class="flex flex-col gap-2">
				<p class="text-sm font-bold text-red-400">Are you sure? This cannot be undone.</p>
				<div class="flex gap-2">
					<Button variant="danger" size="md" onclick={handleReset} disabled={resetting}>
						{resetting ? 'Resetting...' : 'Yes, reset everything'}
					</Button>
					<Button variant="ghost" size="md" onclick={cancelReset}>Cancel</Button>
				</div>
			</div>
		{:else}
			<Button variant="secondary" size="md" onclick={handleReset}>Reset Progress</Button>
		{/if}
	</Card>

	<Card class="p-5">
		<h3 class="text-sm font-bold text-slate-300 mb-1">Navigation</h3>
		<p class="text-xs text-slate-500 mb-3">Quick links to all sections.</p>
		<div class="flex flex-wrap gap-2">
			<Button href="/flow" variant="gold" size="sm">Learn</Button>
			<Button href="/flow/stats" variant="secondary" size="sm">Stats</Button>
			<Button href="/flow/concepts" variant="secondary" size="sm">Concepts</Button>
			<Button href="/flow/words" variant="secondary" size="sm">Words</Button>
			<Button href="/" variant="ghost" size="sm">Home</Button>
		</div>
	</Card>
</div>
