<script lang="ts">
	import { ProgressBar } from '$lib/components/ui/progress';
	import type { UserProgress } from '$lib/stores/user';

	interface Props {
		progress: UserProgress;
	}

	let { progress }: Props = $props();
</script>

<div class="mb-8 flex flex-wrap items-center gap-6 rounded-2xl bg-[#1a2d35] px-6 py-5 shadow-lg shadow-black/20">
	<div class="flex flex-col items-center gap-1">
		<span class="inline-flex h-12 w-12 items-center justify-center rounded-full bg-emerald-500 text-xl font-black text-emerald-950 shadow-md shadow-emerald-500/30">
			{progress.level}
		</span>
		<span class="text-[10px] uppercase tracking-widest text-slate-400 font-bold">Level</span>
	</div>

	<div class="flex flex-1 flex-col gap-1 min-w-[160px]">
		<ProgressBar
			value={progress.xp_into_level}
			max={progress.xp_for_next_level}
			label="{progress.xp_into_level} / {progress.xp_for_next_level} XP"
		/>
	</div>

	<div class="text-center">
		<p class="text-2xl font-black text-amber-400">{progress.xp}</p>
		<p class="text-[10px] uppercase tracking-widest text-slate-500 font-bold">total xp</p>
	</div>

	<div class="flex items-center gap-2">
		{#if progress.streak > 0}
			<span class="text-2xl">🔥</span>
			<div class="text-center">
				<p class="text-2xl font-black text-amber-400">{progress.streak}</p>
				<p class="text-[10px] uppercase tracking-widest text-amber-500/70 font-bold">streak</p>
			</div>
		{:else}
			<span class="text-2xl opacity-40">❄️</span>
			<div class="text-center">
				<p class="text-2xl font-black text-slate-500">0</p>
				<p class="text-[10px] uppercase tracking-widest text-slate-600 font-bold">streak</p>
			</div>
		{/if}
	</div>
</div>
