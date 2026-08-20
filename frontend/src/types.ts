export type Urgency = 'emergency' | 'medical' | 'general' | null;

export interface AuditEvent {
  module: string;
  event_type: string;
  payload: Record<string, unknown>;
  turn_id?: string | null;
}

export interface ChatResponse {
  session_id: string;
  response: string;
  urgency: Urgency;
  events: AuditEvent[];
}

export interface QueuedChatResponse {
  job_id: string;
  session_id: string;
  status: string;
}

export interface JobResponse {
  job_id: string;
  status: 'pending' | 'processing' | 'success' | 'failure';
  result?: ChatResponse | null;
  error?: string | null;
}

export type ChatResult =
  | { kind: 'sync'; data: ChatResponse }
  | { kind: 'queued'; data: QueuedChatResponse };

export type MessageRole = 'user' | 'assistant' | 'error';

export interface Message {
  id: number;
  role: MessageRole;
  text: string;
  thinking?: boolean;
  streaming?: boolean;
  urgency?: Urgency;
  events?: AuditEvent[];
}