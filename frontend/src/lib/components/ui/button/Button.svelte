<script lang="ts">
	import { cn } from '$lib/utils/cn';

	type Variant = 'primary' | 'secondary' | 'ghost' | 'gold' | 'danger';
	type Size = 'sm' | 'md' | 'lg' | 'xl';

	interface Props {
		variant?: Variant;
		size?: Size;
		class?: string;
		href?: string;
		disabled?: boolean;
		onclick?: (e: MouseEvent) => void;
		children?: import('svelte').Snippet;
	}

	let { variant = 'primary', size = 'md', class: className = '', href, disabled = false, onclick, children }: Props = $props();

	const base = 'inline-flex items-center justify-center font-bold transition active:scale-[0.98]';
	const variants: Record<Variant, string> = {
		primary: 'bg-emerald-500 text-emerald-950 shadow-lg shadow-emerald-500/25 hover:bg-emerald-400',
		secondary: 'bg-emerald-500/15 text-emerald-300 hover:bg-emerald-500/25 hover:text-emerald-200',
		ghost: 'bg-slate-500/15 text-slate-300 hover:bg-slate-500/25 hover:text-slate-100',
		gold: 'bg-amber-500 text-amber-950 shadow-lg shadow-amber-500/25 hover:bg-amber-400',
		danger: 'bg-red-500/15 text-red-300 hover:bg-red-500/25',
	};
	const sizes: Record<Size, string> = {
		sm: 'rounded-full px-3 py-1.5 text-xs',
		md: 'rounded-full px-4 py-2 text-sm',
		lg: 'rounded-2xl px-6 py-3 text-base',
		xl: 'rounded-2xl px-8 py-5 text-xl font-black',
	};
</script>

{#if href}
	<a {href} class={cn(base, variants[variant], sizes[size], disabled && 'opacity-50 pointer-events-none', className)}>
		{@render children?.()}
	</a>
{:else}
	<button {disabled} {onclick} class={cn(base, variants[variant], sizes[size], disabled && 'opacity-50', className)}>
		{@render children?.()}
	</button>
{/if}
