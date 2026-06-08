import { api } from './client';
import type {
	ChatResponse,
	ChatHistoryResponse,
	FillBlankFeedback,
	McqFeedback,
	QuizSetFeedback,
	QuizSetNext,
	PlacementFeedback,
	PlacementNext,
	PersonasResponse,
	LearnerStats,
} from './types';

export function sendMessage(message: string): Promise<ChatResponse> {
	return api.post('/chat', { message });
}

export function getChatHistory(): Promise<ChatHistoryResponse> {
	return api.get('/chat/history');
}

// --- Quiz ---
export function answerFillBlank(
	cardId: string,
	blankIdx: number,
	answer: string
): Promise<FillBlankFeedback> {
	return api.post('/quiz/answer', { card_id: cardId, blank_idx: blankIdx, answer });
}

export function answerMcq(cardId: string, selected: number): Promise<McqFeedback> {
	return api.post('/quiz/mcq', { card_id: cardId, selected });
}

export function answerQuizSet(cardId: string, selected: number): Promise<QuizSetFeedback> {
	return api.post('/quiz/set/answer', { card_id: cardId, selected });
}

export function nextQuizSetQuestion(cardId: string): Promise<QuizSetNext> {
	return api.post('/quiz/set/next', { card_id: cardId });
}

export function completeQuiz(cardId: string): Promise<ChatResponse> {
	return api.post('/quiz/complete', { card_id: cardId });
}

// --- Placement ---
export function answerPlacement(cardId: string, selected: number): Promise<PlacementFeedback> {
	return api.post('/placement/answer', { card_id: cardId, selected });
}

export function nextPlacementQuestion(cardId: string): Promise<PlacementNext> {
	return api.post('/placement/next', { card_id: cardId });
}

// --- Personas ---
export function getPersonas(): Promise<PersonasResponse> {
	return api.get('/personas');
}

export function switchPersona(personaId: string): Promise<{ ok: boolean; persona: any }> {
	return api.post('/persona/switch', { persona_id: personaId });
}

export function getCurrentPersona(): Promise<any> {
	return api.get('/persona/current');
}

// --- Stats ---
export function getLearnerStats(): Promise<LearnerStats> {
	return api.get('/learner/stats');
}

// --- Translate ---
export function translateWord(
	text: string,
	context: string = ''
): Promise<{ translation: string }> {
	return api.post('/translate', { text, context });
}
