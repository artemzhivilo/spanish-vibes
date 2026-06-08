const BASE = '/api';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
	const res = await fetch(`${BASE}${path}`, {
		headers: { 'Content-Type': 'application/json', ...init?.headers },
		...init
	});
	if (!res.ok) {
		throw new Error(`API ${res.status}: ${await res.text()}`);
	}
	return res.json();
}

export const api = {
	get: <T>(path: string) => request<T>(path),

	post: <T>(path: string, body?: unknown) =>
		request<T>(path, { method: 'POST', body: body ? JSON.stringify(body) : undefined }),

	postForm: async <T>(path: string, data: Record<string, string>) => {
		const res = await fetch(`${BASE}${path}`, {
			method: 'POST',
			headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
			body: new URLSearchParams(data)
		});
		if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
		return res.json() as Promise<T>;
	}
};
