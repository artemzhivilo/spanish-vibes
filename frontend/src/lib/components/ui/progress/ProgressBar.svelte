<script lang="ts">
	import { cn } from '$lib/utils/cn';

	interface Props {
		value: number;
		max?: number;
		label?: string;
		class?: string;
	}

	let { value, max = 100, label, class: className = '' }: Props = $props();
	let pct = $derived(Math.min(100, (value / max) * 100));
</script>

<div class={cn('relative h-4 w-full overflow-hidden rounded-full bg-[#0f1a1f]', className)}>
	<div
		class="h-full rounded-full bg-gradient-to-r from-emerald-500 to-emerald-400 transition-all duration-500"
		style="width: {pct}%"
	></div>
	{#if label}
		<span class="absolute inset-0 flex items-center justify-center text-[11px] font-bold text-white drop-shadow">
			{label}
		</span>
	{/if}
</div>
