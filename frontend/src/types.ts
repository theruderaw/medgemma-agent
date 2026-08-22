export type Urgency = 'emergency' | 'urgent' | 'routine' | 'self_care' | null;

/** An image picked in the UI, ready to ride along with a chat request. */
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

/** POST /v1/triage — the model only emits urgency; other fields are structural. */
export interface TriageApiResponse {
  urgency: Exclude<Urgency, null>;
  red_flags: string[];
  text_findings: string[];
  image_findings: string[];
  reasoning: string;
  body_part: string | null;
  body_part_confidence: number | null;
  limitations: string[];
  model: string;
  source: 'rules' | 'text';
  image: ImageMeta | null;
}

/** Audit-shaped pipeline event (live via SSE, or inside a completed response). */
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
  /** Pipeline path taken this turn (e.g. medical_specialist, emergency_override). */
  path?: string | null;
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

/** GET /v1/audit row — the durable Postgres audit trail. */
export interface AuditRecord {
  id: number;
  session_id: string | null;
  turn_id: string | null;
  module: string;
  event_type: string;
  payload: Record<string, unknown>;
  created_at: number;
}

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
