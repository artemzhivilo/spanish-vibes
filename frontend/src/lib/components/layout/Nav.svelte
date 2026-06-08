<script lang="ts">
	import { page } from '$app/stores';
	import { Button } from '$lib/components/ui/button';

	interface Props {
		user?: { username: string } | null;
	}

	let { user = null }: Props = $props();

	let currentPath = $derived($page.url.pathname);
</script>

<header class="mb-8 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
	<a href="/" class="flex items-center gap-3 no-underline">
		<span class="inline-flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-500 text-lg font-black text-emerald-950">S</span>
		<div>
			<h1 class="text-2xl font-bold tracking-tight text-slate-50">Spanish Vibes</h1>
			<p class="text-xs text-slate-400">AI-powered language learning</p>
		</div>
	</a>
	<nav class="flex flex-wrap gap-2 text-sm font-bold">
		<Button href="/" variant={currentPath === '/' ? 'primary' : 'secondary'} size="md">Home</Button>
		<Button href="/flow" variant={currentPath.startsWith('/flow') ? 'gold' : 'ghost'} size="md">Flow</Button>
		{#if user}
			<span class="rounded-full bg-slate-500/15 px-4 py-2 text-slate-300">{user.username}</span>
			<Button variant="ghost" size="md">Logout</Button>
		{:else}
			<Button href="/auth/login" variant="ghost" size="md">Log In</Button>
			<Button href="/auth/signup" variant="secondary" size="md">Sign Up</Button>
		{/if}
	</nav>
</header>
