<script lang="ts">
	import { cn } from '$lib/utils/cn';

	interface Props {
		class?: string;
		children?: import('svelte').Snippet;
	}

	let { class: className = '', children }: Props = $props();
</script>

<div class={cn('rounded-2xl bg-[#1a2d35] shadow-lg shadow-black/20', className)}>
	{@render children?.()}
</div>
