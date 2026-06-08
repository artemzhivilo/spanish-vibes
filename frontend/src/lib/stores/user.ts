import { writable } from 'svelte/store';

export interface UserProgress {
	xp: number;
	level: number;
	level_pct: number;
	xp_into_level: number;
	xp_for_next_level: number;
	streak: number;
	concepts_mastered: number;
	total_concepts: number;
	cefr: string;
}

export interface User {
	username: string;
	progress: UserProgress | null;
}

export const user = writable<User | null>(null);
