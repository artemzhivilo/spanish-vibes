export interface Progress {
	xp: number;
	level: number;
	level_pct: number;
	xp_into_level: number;
	xp_for_next_level: number;
	streak: number;
}

export interface ProgressResponse {
	progress: Progress | null;
	concepts_mastered: number;
	total_concepts: number;
	cefr: string;
	user_level: number;
	tier_mastery: Record<string, number>;
	onboarded: boolean;
}

export interface FlowSession {
	session_id: number;
	cards_answered: number;
	correct_count: number;
	streak: number;
	concepts_mastered: number;
	total_concepts: number;
	cefr: string;
}

export interface FlowCard {
	card_type: string;
	concept_id: string;
	question: string;
	correct_answer: string;
	options: string[];
	option_misconceptions: Record<string, string>;
	difficulty: number;
	mcq_card_id: number | null;
	teach_content: string;
	word_id: number | null;
	word_spanish: string;
	word_english: string;
	word_emoji: string | null;
	word_sentence: string;
	word_pairs: Array<{ spanish: string; english: string }>;
	scrambled_words: string[];
	correct_sentence: string;
	english_prompt: string;
	conversation_type: string;
	interest_topics: string[];
	target_concept_id: string | null;
}

export interface CardResponse {
	status: 'ok' | 'loading' | 'empty';
	card?: FlowCard;
	concept_name?: string;
	session_id?: number;
	retry?: number;
}

export interface AnswerResponse {
	is_correct: boolean;
	correct_answer: string;
	concept_id: string;
	concept_name: string;
	xp_earned: number;
	streak: number;
	cards_answered: number;
	concepts_mastered: number;
	total_concepts: number;
	misconception_concept: string | null;
}

export interface ConceptInfo {
	id: string;
	name: string;
	description: string;
	difficulty_level: number;
	mastery: number;
	attempts: number;
	correct: number;
	is_mastered: boolean;
	teach_shown: boolean;
}

export interface TierStats {
	total: number;
	mastered: number;
	concepts: Array<{
		id: string;
		name: string;
		mastery: number;
		is_mastered: boolean;
	}>;
}

export interface StatsResponse {
	progress: { xp: number; level: number; streak: number } | null;
	concepts_mastered: number;
	total_concepts: number;
	cefr: string;
	tiers: Record<string, TierStats>;
}

export interface WordInfo {
	id: number;
	spanish: string;
	english: string;
	emoji: string | null;
	concept_id: string;
	status: string;
	times_seen: number;
	times_correct: number;
}
