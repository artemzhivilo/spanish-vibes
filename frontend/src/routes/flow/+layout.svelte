<script lang="ts">
	import { page } from '$app/stores';
	import { onMount } from 'svelte';

	let { children } = $props();

	let currentPath = $derived($page.url.pathname);
	let navEl: HTMLElement;

	onMount(() => {
		if (navEl) {
			const h = navEl.getBoundingClientRect().height;
			document.documentElement.style.setProperty('--tab-bar-h', `${h}px`);
		}
	});

	const tabs = [
		{ href: '/flow', label: 'Chat', icon: '💬' },
		{ href: '/flow/stats', label: 'Stats', icon: '📊' },
		{ href: '/flow/words', label: 'Words', icon: '📝' },
		{ href: '/flow/settings', label: 'Settings', icon: '⚙' },
	];

	function isActive(href: string): boolean {
		if (href === '/flow') return currentPath === '/flow';
		return currentPath.startsWith(href);
	}

	let isChatPage = $derived(currentPath === '/flow');
</script>

{#if isChatPage}
	<!-- Chat page: fixed position so it sits exactly between top edge and tab bar -->
	<div style="position: fixed; top: 0; left: 0; right: 0; bottom: var(--tab-bar-h, 68px); display: flex; flex-direction: column; overflow: hidden;">
		{@render children()}
	</div>
{:else}
	<div class="p-4" style="min-height: calc(100dvh - var(--tab-bar-h, 68px)); padding-bottom: var(--tab-bar-h, 68px);">
		{@render children()}
	</div>
{/if}

<nav bind:this={navEl} class="fixed bottom-0 left-0 right-0 z-40 border-t" style="background: #FBF7F0; border-color: rgba(0,0,0,0.08);">
	<div class="mx-auto max-w-4xl flex items-center justify-around px-2 py-2">
		{#each tabs as tab}
			<a
				href={tab.href}
				class="flex flex-col items-center gap-0.5 px-3 py-1 rounded-lg text-[11px] font-bold transition"
				style={isActive(tab.href)
					? 'color: #C8553D;'
					: 'color: rgba(60,45,30,0.45);'}
			>
				<span class="text-base">{tab.icon}</span>
				<span>{tab.label}</span>
			</a>
		{/each}
	</div>
</nav>
