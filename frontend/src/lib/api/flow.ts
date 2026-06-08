import { api } from './client';
import type {
	ProgressResponse,
	FlowSession,
	CardResponse,
	AnswerResponse,
	StatsResponse,
	ConceptInfo,
	WordInfo,
	FlowCard,
} from './types';

export async function getProgress(): Promise<ProgressResponse> {
	return api.get('/progress');
}

export async function startSession(): Promise<FlowSession> {
	return api.post('/flow/session');
}

export async function getNextCard(sessionId: number, retry = 0): Promise<CardResponse> {
	return api.get(`/flow/card?session_id=${sessionId}&retry=${retry}`);
}

export async function submitAnswer(
	sessionId: number,
	chosenOption: string,
	cardData: FlowCard,
	startTime: number
): Promise<AnswerResponse> {
	return api.post('/flow/answer', {
		session_id: sessionId,
		chosen_option: chosenOption,
		card_data: cardData,
		start_time: startTime,
	});
}

export async function markTeachSeen(sessionId: number, conceptId: string): Promise<void> {
	await api.post(`/flow/teach-seen?session_id=${sessionId}&concept_id=${conceptId}`);
}

export async function getStats(): Promise<StatsResponse> {
	return api.get('/stats');
}

export async function getConcepts(): Promise<{ concepts: ConceptInfo[] }> {
	return api.get('/concepts');
}

export async function getWords(): Promise<{ words: WordInfo[] }> {
	return api.get('/words');
}
