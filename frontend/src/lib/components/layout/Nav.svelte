<script lang="ts">
	import { page } from '$app/stores';

	interface Props {
		user?: { username: string } | null;
	}

	let { user = null }: Props = $props();

	let currentPath = $derived($page.url.pathname);
</script>

<header class="mb-8 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
	<a href="/" class="flex items-center gap-3 no-underline">
		<span class="inline-flex h-10 w-10 items-center justify-center rounded-xl text-lg font-black text-white" style="background: #C8553D;">S</span>
		<div>
			<h1 class="text-2xl font-bold tracking-tight" style="color: #1a1410;">Spanish Vibes</h1>
			<p class="text-xs" style="color: rgba(60,45,30,0.55);">AI-powered language learning</p>
		</div>
	</a>
	<nav class="flex flex-wrap gap-2 text-sm font-bold">
		<a href="/" class="rounded-full px-4 py-2 transition" style={currentPath === '/' ? 'background: #C8553D; color: white;' : 'background: rgba(0,0,0,0.05); color: #1a1410;'}>Home</a>
		<a href="/flow" class="rounded-full px-4 py-2 transition" style={currentPath.startsWith('/flow') ? 'background: #C8553D; color: white;' : 'background: rgba(0,0,0,0.05); color: #1a1410;'}>Flow</a>
		{#if user}
			<span class="rounded-full px-4 py-2" style="background: rgba(0,0,0,0.05); color: rgba(60,45,30,0.7);">{user.username}</span>
		{:else}
			<a href="/auth/login" class="rounded-full px-4 py-2 transition" style="color: rgba(60,45,30,0.7);">Log In</a>
			<a href="/auth/signup" class="rounded-full px-4 py-2 transition" style="background: rgba(0,0,0,0.05); color: #1a1410;">Sign Up</a>
		{/if}
	</nav>
</header>
