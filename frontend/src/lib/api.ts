import type {
  AttachedImage,
  AuditEvent,
  AuditRecord,
  ChatResponse,
  JobResponse,
  QueuedChatResponse,
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
// Chat turns: always enqueued (Celery); the emergency floor answers 200 sync.

export type EnqueueResult =
  | { kind: 'sync'; data: ChatResponse }
  | { kind: 'queued'; data: QueuedChatResponse };

/**
 * POST /v1/chat?triage=… — enqueue one turn.
 *
 * `202` → `{ kind: 'queued' }`; watch the job via `watchJob` (or poll).
 * `200` → `{ kind: 'sync' }`: the deterministic emergency floor matched and
 * answered without the queue. Throws ApiError for 410/422/503.
 */
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
// Job watching: SSE first (with Last-Event-ID replay), polling as fallback.

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
 * GET /v1/jobs/{id}/events over a native EventSource.
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
      handlers.onError(
        typeof p?.error === 'string' && p.error ? p.error : 'Turn failed.',
      );
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

// ---------------------------------------------------------------------------
// Other endpoints

export async function pollJob(jobId: string): Promise<JobResponse> {
  const res = await fetch(`/v1/jobs/${encodeURIComponent(jobId)}`);
  if (!res.ok) {
    const data = (await res.json().catch(() => ({}))) as { detail?: string };
    throw new ApiError(res.status, data.detail ?? `Job lookup failed (${res.status})`);
  }
  return (await res.json()) as JobResponse;
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

export async function resetSession(sessionId: string): Promise<void> {
  await fetch(`/v1/sessions/${encodeURIComponent(sessionId)}`, { method: 'DELETE' });
}

export async function health(): Promise<boolean> {
  try {
    const res = await fetch('/health');
    return res.ok;
  } catch {
    return false;
  }
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
