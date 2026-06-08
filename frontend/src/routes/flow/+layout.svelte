<script lang="ts">
	import { page } from '$app/stores';

	let { children } = $props();

	let currentPath = $derived($page.url.pathname);

	const tabs = [
		{ href: '/flow', label: 'Learn', icon: '▶' },
		{ href: '/flow/stats', label: 'Stats', icon: '📊' },
		{ href: '/flow/concepts', label: 'Concepts', icon: '🧠' },
		{ href: '/flow/words', label: 'Words', icon: '📝' },
		{ href: '/flow/settings', label: 'Settings', icon: '⚙' },
	];

	function isActive(href: string): boolean {
		if (href === '/flow') return currentPath === '/flow';
		return currentPath.startsWith(href);
	}
</script>

<div class="flex flex-col min-h-[calc(100vh-4rem)] pb-16">
	<div class="flex-1">
		{@render children()}
	</div>

	<nav class="fixed bottom-0 left-0 right-0 bg-[#0f1a1f] border-t border-[#1e3a47] z-40">
		<div class="mx-auto max-w-4xl flex items-center justify-around px-2 py-2">
			{#each tabs as tab}
				<a
					href={tab.href}
					class="flex flex-col items-center gap-0.5 px-3 py-1 rounded-lg text-[11px] font-bold transition {isActive(tab.href) ? 'text-emerald-400' : 'text-slate-500 hover:text-slate-300'}"
				>
					<span class="text-base">{tab.icon}</span>
					<span>{tab.label}</span>
				</a>
			{/each}
		</div>
	</nav>
</div>
