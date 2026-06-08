<script lang="ts">
	import { api } from '$lib/api/client';

	let resetting = $state(false);
	let resetDone = $state(false);
	let confirmReset = $state(false);

	async function handleReset() {
		if (!confirmReset) {
			confirmReset = true;
			return;
		}
		resetting = true;
		await api.post('/reset-progress', {});
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
	<h2 class="text-xl font-black" style="color: #1a1410; font-family: var(--font-serif);">Settings</h2>

	<div class="rounded-2xl p-5" style="background: white; box-shadow: 0 1px 0 rgba(0,0,0,0.02), 0 4px 14px rgba(0,0,0,0.04);">
		<h3 class="text-sm font-bold mb-1" style="color: #1a1410;">Reset Progress</h3>
		<p class="text-xs mb-4" style="color: rgba(60,45,30,0.55);">
			Clear all learning data — vocabulary, grammar status, conversation history, CEFR level. Starts you fresh.
		</p>

		{#if resetDone}
			<div class="rounded-xl px-4 py-3 text-sm font-bold" style="background: rgba(45,90,61,0.08); color: #2D5A3D;">
				Progress reset! <a href="/flow" class="underline">Start fresh</a>
			</div>
		{:else if confirmReset}
			<div class="flex flex-col gap-2">
				<p class="text-sm font-bold" style="color: #C8553D;">Are you sure? This cannot be undone.</p>
				<div class="flex gap-2">
					<button
						class="rounded-xl px-4 py-2 text-sm font-bold text-white transition active:scale-[0.98]"
						style="background: #C8553D;"
						onclick={handleReset}
						disabled={resetting}
					>
						{resetting ? 'Resetting...' : 'Yes, reset everything'}
					</button>
					<button
						class="rounded-xl px-4 py-2 text-sm font-bold transition"
						style="background: rgba(0,0,0,0.05); color: rgba(60,45,30,0.7);"
						onclick={cancelReset}
					>
						Cancel
					</button>
				</div>
			</div>
		{:else}
			<button
				class="rounded-xl px-4 py-2 text-sm font-bold transition"
				style="background: rgba(0,0,0,0.05); color: #1a1410;"
				onclick={handleReset}
			>
				Reset Progress
			</button>
		{/if}
	</div>

	<div class="rounded-2xl p-5" style="background: white; box-shadow: 0 1px 0 rgba(0,0,0,0.02), 0 4px 14px rgba(0,0,0,0.04);">
		<h3 class="text-sm font-bold mb-1" style="color: #1a1410;">Navigation</h3>
		<p class="text-xs mb-3" style="color: rgba(60,45,30,0.55);">Quick links to all sections.</p>
		<div class="flex flex-wrap gap-2">
			<a href="/flow" class="rounded-full px-3 py-1.5 text-xs font-bold text-white" style="background: #C8553D;">Chat</a>
			<a href="/flow/stats" class="rounded-full px-3 py-1.5 text-xs font-bold" style="background: rgba(0,0,0,0.05); color: #1a1410;">Stats</a>
			<a href="/flow/words" class="rounded-full px-3 py-1.5 text-xs font-bold" style="background: rgba(0,0,0,0.05); color: #1a1410;">Words</a>
			<a href="/" class="rounded-full px-3 py-1.5 text-xs font-bold" style="color: rgba(60,45,30,0.55);">Home</a>
		</div>
	</div>
</div>
