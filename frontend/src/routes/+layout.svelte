<script lang="ts">
	import '../app.css';
	import { page } from '$app/stores';
	import Nav from '$lib/components/layout/Nav.svelte';

	let { children } = $props();

	let isFlowPage = $derived($page.url.pathname.startsWith('/flow'));
</script>

<div class="min-h-screen" style="background: #FBF7F0;">
	<main class="mx-auto flex min-h-screen max-w-4xl flex-col px-4 py-8 sm:px-6">
		{#if !isFlowPage}
			<Nav />
		{/if}
		<section class="flex-1">
			{@render children()}
		</section>
	</main>
</div>
