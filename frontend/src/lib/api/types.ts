// --- Persona ---
export interface Persona {
	id: string;
	name: string;
	region: string;
	bio: string;
	welcome_sub: string;
	bubble_bg: string;
	bubble_border: string;
	bubble_name_color: string;
	avatar_template?: string;
}

// --- Chat ---
export interface ChatMessage {
	role: 'user' | 'persona';
	text: string;
}

export interface ActivityCard {
	type: 'fill_blank' | 'mcq' | 'flashcard_set' | 'grammar_note' | 'quiz_set' | 'placement';
	id: string;
	intro?: string;
	// fill_blank
	sentences?: Array<{
		idx: number;
		text_with_blank: string;
		hint?: string;
		answer?: string;
	}>;
	// mcq
	question?: string;
	options?: string[];
	// flashcard_set
	cards?: Array<{
		front: string;
		back: string;
		example?: string;
	}>;
	// grammar_note
	title?: string;
	explanation?: string;
	examples?: Array<{ spanish: string; english: string }>;
	// quiz_set
	topic?: string;
	current?: number;
	total?: number;
	// placement
}

export interface ChatResponse {
	text: string;
	cards: ActivityCard[];
	persona: Persona;
}

export interface ChatHistoryResponse {
	messages: ChatMessage[];
	persona: Persona;
}

// --- Quiz feedback ---
export interface FillBlankFeedback {
	correct: boolean;
	correct_answer: string;
	last: boolean;
}

export interface McqFeedback {
	correct: boolean;
	explanation: string;
	correct_index: number;
	selected: number;
}

export interface QuizSetFeedback {
	correct: boolean;
	correct_answer: string;
	selected_answer: string;
	has_next: boolean;
	is_retry: boolean;
}

export interface QuizSetNext {
	complete: boolean;
	question?: {
		question: string;
		options: string[];
		correct_index: number;
		is_retry?: boolean;
	};
	current?: number;
	total?: number;
	is_retry?: boolean;
	correct_count?: number;
}

export interface PlacementFeedback {
	correct: boolean;
	correct_answer: string;
	selected_answer: string;
	has_next: boolean;
}

export interface PlacementNext {
	complete: boolean;
	question?: { question: string; options: string[] };
	current?: number;
	total?: number;
	level?: string;
	breakdown?: Array<{ label: string; correct: number; total: number; pct: number }>;
	gaps?: string[];
}

// --- Personas ---
export interface PersonasResponse {
	personas: Record<string, Persona>;
	active: string;
}

// --- Stats ---
export interface LearnerStats {
	profile: {
		display_name: string | null;
		cefr_level: string;
		interests: string[] | null;
	};
	grammar: Record<string, { status: string }>;
	vocabulary: { total: number; due: number };
	words: Array<{
		word: string;
		translation: string;
		domain: string | null;
		repetitions: number;
		times_correct: number;
		times_wrong: number;
	}>;
}
