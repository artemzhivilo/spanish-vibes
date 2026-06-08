<script lang="ts">
	import { cn } from '$lib/utils/cn';

	type Color = 'emerald' | 'amber' | 'sky' | 'violet' | 'indigo' | 'slate' | 'red';

	interface Props {
		color?: Color;
		class?: string;
		children?: import('svelte').Snippet;
	}

	let { color = 'emerald', class: className = '', children }: Props = $props();

	const colors: Record<Color, string> = {
		emerald: 'bg-emerald-500/15 text-emerald-300',
		amber: 'bg-amber-500/15 text-amber-300',
		sky: 'bg-sky-500/15 text-sky-300',
		violet: 'bg-violet-500/15 text-violet-300',
		indigo: 'bg-indigo-500/15 text-indigo-300',
		slate: 'bg-slate-500/15 text-slate-300',
		red: 'bg-red-500/15 text-red-300',
	};
</script>

<span class={cn('rounded-full px-3 py-1 text-xs font-bold', colors[color], className)}>
	{@render children?.()}
</span>
