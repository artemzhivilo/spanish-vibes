<script lang="ts">
	import { onMount } from 'svelte';
	import { getLearnerStats } from '$lib/api/chat';
	import type { LearnerStats } from '$lib/api/types';

	let data = $state<LearnerStats | null>(null);
	let loading = $state(true);

	onMount(async () => {
		try {
			data = await getLearnerStats();
		} catch (e) {
			console.error('Failed to load stats:', e);
		}
		loading = false;
	});

	function statusLabel(status: string): string {
		const labels: Record<string, string> = {
			solid: 'Solid',
			shaky: 'Shaky',
			gap: 'Gap',
			untested: 'Untested',
		};
		return labels[status] ?? status;
	}

	function statusColor(status: string): string {
		const colors: Record<string, string> = {
			solid: '#2D5A3D',
			shaky: '#C8553D',
			gap: '#C8553D',
			untested: 'rgba(60,45,30,0.35)',
		};
		return colors[status] ?? 'rgba(60,45,30,0.35)';
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

		<!-- Top-level stats -->
		<div class="grid grid-cols-3 gap-3">
			<div class="rounded-2xl p-4 text-center" style="background: white; box-shadow: 0 1px 0 rgba(0,0,0,0.02), 0 4px 14px rgba(0,0,0,0.04);">
				<p class="text-2xl font-black" style="color: #C8553D;">{data.profile.cefr_level}</p>
				<p class="text-[10px] uppercase tracking-widest font-bold" style="color: rgba(60,45,30,0.45);">Level</p>
			</div>
			<div class="rounded-2xl p-4 text-center" style="background: white; box-shadow: 0 1px 0 rgba(0,0,0,0.02), 0 4px 14px rgba(0,0,0,0.04);">
				<p class="text-2xl font-black" style="color: #C8553D;">{data.vocabulary.total}</p>
				<p class="text-[10px] uppercase tracking-widest font-bold" style="color: rgba(60,45,30,0.45);">Words</p>
			</div>
			<div class="rounded-2xl p-4 text-center" style="background: white; box-shadow: 0 1px 0 rgba(0,0,0,0.02), 0 4px 14px rgba(0,0,0,0.04);">
				<p class="text-2xl font-black" style="color: #C8553D;">{data.vocabulary.due}</p>
				<p class="text-[10px] uppercase tracking-widest font-bold" style="color: rgba(60,45,30,0.45);">Due</p>
			</div>
		</div>

		<!-- Interests -->
		{#if data.profile.interests?.length}
			<div class="rounded-2xl p-5" style="background: white; box-shadow: 0 1px 0 rgba(0,0,0,0.02), 0 4px 14px rgba(0,0,0,0.04);">
				<h3 class="text-sm font-bold mb-2" style="color: #1a1410;">Interests</h3>
				<div class="flex flex-wrap gap-2">
					{#each data.profile.interests as interest}
						<span class="rounded-full px-3 py-1 text-xs font-bold" style="background: rgba(200,85,61,0.08); color: #C8553D;">
							{interest}
						</span>
					{/each}
				</div>
			</div>
		{/if}

		<!-- Grammar -->
		{#if Object.keys(data.grammar).length > 0}
			<div class="rounded-2xl p-5" style="background: white; box-shadow: 0 1px 0 rgba(0,0,0,0.02), 0 4px 14px rgba(0,0,0,0.04);">
				<h3 class="text-sm font-bold mb-3" style="color: #1a1410;">Grammar</h3>
				<div class="grid gap-1.5">
					{#each Object.entries(data.grammar) as [topic, info]}
						<div class="flex items-center justify-between py-1.5 px-3 rounded-lg" style="background: #FBF7F0;">
							<span class="text-sm" style="color: #1a1410;">{topic.replace(/_/g, ' ')}</span>
							<span class="text-[10px] font-bold rounded-full px-2 py-0.5" style="color: {statusColor(info.status)}; background: {info.status === 'solid' ? 'rgba(45,90,61,0.08)' : info.status === 'gap' ? 'rgba(200,85,61,0.08)' : 'rgba(0,0,0,0.04)'};">
								{statusLabel(info.status)}
							</span>
						</div>
					{/each}
				</div>
			</div>
		{/if}
	</div>
{/if}
