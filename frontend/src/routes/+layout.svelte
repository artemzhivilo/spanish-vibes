<script lang="ts">
	import '../app.css';
	import { page } from '$app/stores';
	import Nav from '$lib/components/layout/Nav.svelte';

	let { children } = $props();

	let isFlowPage = $derived($page.url.pathname.startsWith('/flow'));
</script>

<div class="bg-[#131F24] text-slate-50 min-h-screen">
	<main class="mx-auto flex min-h-screen max-w-4xl flex-col px-4 py-8 sm:px-6">
		{#if !isFlowPage}
			<Nav />
		{/if}
		<section class="flex-1">
			{@render children()}
		</section>
	</main>
</div>
