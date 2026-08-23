// ---------------------------------------------------------------------------
// Transport layer — one function per backend endpoint. All UI data flow goes
// through here; components never call fetch directly.
//
// Chat turns are ALWAYS enqueued (Celery) except the deterministic emergency
// floor, which answers synchronously with 200. Job progress arrives over SSE
// (GET /v1/jobs/{id}/events) with polling as the resilience fallback.

import type {
  AttachedImage,
  AuditEvent,
  AuditRecord,
  ChatResponse,
  FeatureInfo,
  JobResponse,
  QueuedChatResponse,
  RecentChat,
  SessionHistory,
  TriageApiResponse,
} from '../types';

export class ApiError extends Error {
  readonly status: number;
  readonly gone: boolean;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.gone = status === 410;
  }
}

async function json<T>(res: Response): Promise<T> {
  const data = (await res.json().catch(() => ({}))) as { detail?: string } & T;
  if (!res.ok) {
    throw new ApiError(res.status, data.detail ?? `Request failed (${res.status})`);
  }
  return data;
}

function imageFields(image?: AttachedImage) {
  return image ? { image_b64: image.b64, image_mime: image.mime } : {};
}

// ---------------------------------------------------------------------------
// POST /v1/chat — enqueue a turn (200 = sync emergency response).

export type EnqueueResult =
  | { kind: 'sync'; data: ChatResponse }
  | { kind: 'queued'; data: QueuedChatResponse };

export async function enqueueTurn(
  message: string,
  sessionId: string | null,
  image?: AttachedImage,
  triage = false,
): Promise<EnqueueResult> {
  const res = await fetch(`/v1/chat${triage ? '?triage=true' : ''}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, session_id: sessionId, ...imageFields(image) }),
  });
  if (res.status === 202) {
    return { kind: 'queued', data: await json<QueuedChatResponse>(res) };
  }
  return { kind: 'sync', data: await json<ChatResponse>(res) };
}

// ---------------------------------------------------------------------------
// GET /v1/jobs/{id}/events — SSE with Last-Event-ID replay.

export interface JobStreamHandlers {
  onPipeline?: (event: AuditEvent) => void;
  /** MedGemma clinical-note deltas while the note is being written. */
  onSpecialistToken?: (delta: string) => void;
  /** Final-reply deltas. */
  onToken?: (delta: string) => void;
  onResult: (data: ChatResponse) => void;
  onError: (message: string) => void;
  /**
   * The stream died permanently (repeated connection failures or a hard
   * close). Callers should fall back to polling.
   */
  onConnectionLost?: () => void;
}

const MAX_SSE_FAILURES = 3;

/**
 * Watch one job over a native EventSource.
 *
 * The backend emits named SSE frames (`pipeline`, `specialist_token`, `token`,
 * `result`, `error`) with `id:` lines, so browser auto-reconnect replays
 * anything missed while disconnected. Returns a `close()` that stops watching.
 */
export function watchJob(jobId: string, handlers: JobStreamHandlers): () => void {
  const es = new EventSource(`/v1/jobs/${encodeURIComponent(jobId)}/events`);
  let closed = false;
  let failures = 0;

  const parse = (e: MessageEvent): unknown | null => {
    try {
      return JSON.parse(e.data as string);
    } catch {
      return null;
    }
  };

  const close = () => {
    if (!closed) {
      closed = true;
      es.close();
    }
  };

  const contentFrame = (e: MessageEvent): string | null => {
    const p = parse(e) as { content?: unknown } | null;
    return typeof p?.content === 'string' && p.content ? p.content : null;
  };

  es.addEventListener('open', () => {
    failures = 0; // connection (re)established
  });

  es.addEventListener('pipeline', (e) => {
    const p = parse(e as MessageEvent) as AuditEvent | null;
    if (p && typeof p.event_type === 'string') handlers.onPipeline?.(p);
  });

  es.addEventListener('specialist_token', (e) => {
    const delta = contentFrame(e as MessageEvent);
    if (delta) handlers.onSpecialistToken?.(delta);
  });

  es.addEventListener('token', (e) => {
    const delta = contentFrame(e as MessageEvent);
    if (delta) handlers.onToken?.(delta);
  });

  es.addEventListener('result', (e) => {
    const p = parse(e as MessageEvent) as ChatResponse | null;
    close();
    if (p && typeof p.response === 'string') handlers.onResult(p);
    else handlers.onError('Turn finished with an unreadable result.');
  });

  // Our terminal failure frame is named `error` too — same channel the browser
  // uses for connection failures. Only frames carrying data are ours; bare
  // events are transport errors (the browser auto-reconnects those).
  es.addEventListener('error', (e) => {
    if (closed) return;
    const me = e as MessageEvent;
    if (typeof me.data === 'string' && me.data) {
      const p = parse(me) as { error?: unknown } | null;
      close();
      handlers.onError(typeof p?.error === 'string' && p.error ? p.error : 'Turn failed.');
      return;
    }
    if (es.readyState === EventSource.CLOSED) {
      // HTTP-level rejection (e.g. 404/500): EventSource will not retry.
      close();
      handlers.onConnectionLost?.();
      return;
    }
    failures += 1;
    if (failures >= MAX_SSE_FAILURES) {
      // The stream keeps failing to open — stop retrying and let polling take over.
      close();
      handlers.onConnectionLost?.();
    }
    // Otherwise let the browser retry with replay.
  });

  return close;
}

/** Polling fallback when SSE is unavailable. */
export async function pollUntilDone(
  jobId: string,
  intervalMs = 600,
  timeoutMs = 180_000,
): Promise<ChatResponse> {
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    await new Promise((r) => setTimeout(r, intervalMs));
    if (Date.now() > deadline) {
      throw new Error('Timed out waiting for the turn to finish.');
    }
    const job = await pollJob(jobId).catch((err) => {
      if (err instanceof ApiError && err.status === 404) return null; // brief visibility lag
      throw err;
    });
    if (!job) continue;
    if (job.status === 'success' && job.result) return job.result;
    if (job.status === 'failure') throw new Error(job.error ?? 'Turn failed');
  }
}

export async function pollJob(jobId: string): Promise<JobResponse> {
  const res = await fetch(`/v1/jobs/${encodeURIComponent(jobId)}`);
  if (!res.ok) {
    const data = (await res.json().catch(() => ({}))) as { detail?: string };
    throw new ApiError(res.status, data.detail ?? `Job lookup failed (${res.status})`);
  }
  return (await res.json()) as JobResponse;
}

// ---------------------------------------------------------------------------
// Other endpoints.

/** GET /health — API up + Redis broker reachable. */
export async function health(): Promise<boolean> {
  try {
    const res = await fetch('/health');
    return res.ok;
  } catch {
    return false;
  }
}

/**
 * POST /v1/triage — stateless urgency classification, no session and no
 * synthesis. Text-only by contract: an attached image is stored and audited
 * but never classified.
 */
export async function triageCheck(message: string, image?: AttachedImage): Promise<TriageApiResponse> {
  const res = await fetch('/v1/triage', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, ...imageFields(image) }),
  });
  return json<TriageApiResponse>(res);
}

/** DELETE /v1/sessions/{id} — drop the conversation server-side. */
export async function resetSession(sessionId: string): Promise<void> {
  await fetch(`/v1/sessions/${encodeURIComponent(sessionId)}`, { method: 'DELETE' });
}

/** GET /v1/audit — newest-first audit trail, optionally scoped to a session id. */
export async function fetchAuditEvents(
  opts: { id?: string | null; limit?: number } = {},
): Promise<AuditRecord[]> {
  const q = new URLSearchParams();
  if (opts.id) q.set('id', opts.id);
  if (opts.limit != null) q.set('limit', String(opts.limit));
  const qs = q.toString();
  const res = await fetch(`/v1/audit${qs ? `?${qs}` : ''}`);
  const data = await json<{ events: AuditRecord[] }>(res);
  return data.events;
}

// ---------------------------------------------------------------------------
// Feature add-ons: per-session toggles backed by feature_settings.

/** GET /v1/features — registered add-ons; `sessionId` scopes the enabled flags. */
export async function fetchFeatures(sessionId: string | null): Promise<FeatureInfo[]> {
  const qs = sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : '';
  const res = await fetch(`/v1/features${qs}`);
  const data = await json<{ features: FeatureInfo[] }>(res);
  return data.features;
}

/**
 * POST /v1/features/{name} — toggle one add-on for the session.
 * Throws ApiError (404 unknown feature/session); callers roll back optimistically.
 */
export async function toggleFeature(
  name: string,
  enabled: boolean,
  sessionId: string,
): Promise<FeatureInfo> {
  const res = await fetch(
    `/v1/features/${encodeURIComponent(name)}?session_id=${encodeURIComponent(sessionId)}`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled }),
    },
  );
  return json<FeatureInfo>(res);
}

/** GET /v1/sessions/{id}/messages — persisted conversation, oldest first. */
export async function fetchSessionHistory(sessionId: string): Promise<SessionHistory> {
  const res = await fetch(`/v1/sessions/${encodeURIComponent(sessionId)}/messages`);
  return json<SessionHistory>(res);
}

/** GET /v1/sessions/recent — most recently active conversations, newest first. */
export async function fetchRecentChats(limit = 20): Promise<RecentChat[]> {
  const res = await fetch(`/v1/sessions/recent?limit=${limit}`);
  const data = await json<{ chats: RecentChat[] }>(res);
  return data.chats;
}
