export type Urgency = 'emergency' | 'urgent' | 'routine' | 'self_care' | null;

/** An image picked in the UI, ready to ride along with a chat/triage request. */
export interface AttachedImage {
  /** Base64 payload (no data: prefix). */
  b64: string;
  mime: string;
  /** data: URL for local preview rendering. */
  previewUrl: string;
}

export interface ImageMeta {
  path: string;
  sha256: string;
  mime: string;
  size_bytes: number;
}

export interface TriageApiResponse {
  urgency: Exclude<Urgency, null>;
  red_flags: string[];
  text_findings: string[];
  image_findings: string[];
  reasoning: string;
  model: string;
  source: 'rules' | 'text' | 'vision';
  image: ImageMeta | null;
}

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
  /** Client-side preview of an image attached to a user message. */
  imagePreview?: string;
  /** MedGemma clinical note, accumulated live from specialist_token events. */
  specialistNote?: string;
  specialistStreaming?: boolean;
}