// ---------------------------------------------------------------------------
// Wire types — mirror the FastAPI schemas exactly. UI-only types live next to
// their components.

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

/** Structured specialist artifact — delivered via the `structured` SSE frame,
 * the final turn result, and persisted history rows. */
export interface StructuredPayload {
  kind: 'prescription' | string;
  data: Record<string, unknown>;
}

/** One transcribed medication entry (all fields nullable = unreadable). */
export interface PrescriptionMedication {
  strength?: string | null;
  dose?: string | null;
  frequency?: string | null;
  duration?: string | null;
  instructions?: string | null;
}

/** kind:"prescription" data shape — medications keyed by transcribed name,
 * plus deterministic clarification prompts for unreadable fields. */
export interface PrescriptionData {
  medications: Record<string, PrescriptionMedication>;
  clarifications?: string[];
}

export interface ChatResponse {
  session_id: string;
  response: string;
  urgency: Urgency;
  events: AuditEvent[];
  /** Pipeline path taken this turn (e.g. medical_specialist, emergency_override). */
  path?: string | null;
  /** Structured artifact for this turn (prescription transcription etc.). */
  structured?: StructuredPayload | null;
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

/** GET /v1/sessions/{id}/messages row — persisted conversation turn. */
export interface SessionMessage {
  role: 'user' | 'assistant';
  content: string;
  /** Pipeline turn that produced this message (absent on legacy rows). */
  turn_id?: string | null;
  /** Structured artifact attached to this assistant message. */
  structured?: StructuredPayload | null;
}

export interface SessionHistory {
  session_id: string;
  created_at: number;
  last_activity: number;
  messages: SessionMessage[];
}

/** GET /v1/sessions/recent entry — one recently active conversation. */
export interface RecentChat {
  session_id: string;
  created_at: number;
  last_activity: number;
  message_count: number;
  preview?: string | null;
}

/** GET /v1/addons entry — one registered add-on and its session toggle state. */
export interface AddonInfo {
  name: string;
  description: string;
  enabled: boolean;
  disclaimer_level: 'standard' | 'high';
}

/** GET /v1/config — public upload limits the composer pre-checks against. */
export interface AppConfig {
  image_max_bytes: number;
  image_allowed_mime: string[];
}
