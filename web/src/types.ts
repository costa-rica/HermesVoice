export type TurnState =
  | 'idle'
  | 'recording'
  | 'transcribing'
  | 'thinking'
  | 'speaking'
  | 'error';

export type ConnectionState = 'disconnected' | 'connecting' | 'connected';

export interface WsSessionStarted {
  event: 'session_started';
  conversation_id: string;
}

export interface WsTranscript {
  event: 'transcript';
  text: string;
}

export interface WsTurnStarted {
  event: 'turn_started';
}

export interface WsTurnCompleted {
  event: 'turn_completed';
}

export interface WsTurnEnd {
  event: 'turn_end';
}

export interface WsError {
  event: 'error';
  error: { code: string; message: string; status: number };
}

export type WsJsonFrame =
  | WsSessionStarted
  | WsTranscript
  | WsTurnStarted
  | WsTurnCompleted
  | WsTurnEnd
  | WsError
  | { event: string; [key: string]: unknown };

export interface LatencyTimings {
  utteranceEndAt?: number;
  transcriptAt?: number;
  firstAudioAt?: number;
  turnEndAt?: number;
}

export type ChatMessage = { role: 'user' | 'assistant'; text: string; ts: number };
