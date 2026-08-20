import type { ChatResponse, ChatResult, JobResponse, QueuedChatResponse } from '../types';

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

export async function sendMessage(message: string, sessionId: string | null): Promise<ChatResult> {
  const res = await fetch('/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, session_id: sessionId }),
  });
  if (res.status === 202) {
    return { kind: 'queued', data: await json<QueuedChatResponse>(res) };
  }
  return { kind: 'sync', data: await json<ChatResponse>(res) };
}

export async function pollJob(jobId: string): Promise<JobResponse> {
  const res = await fetch(`/jobs/${encodeURIComponent(jobId)}`);
  if (!res.ok) {
    const data = (await res.json().catch(() => ({}))) as { detail?: string };
    throw new ApiError(res.status, data.detail ?? `Job lookup failed (${res.status})`);
  }
  return (await res.json()) as JobResponse;
}

export async function resetSession(sessionId: string): Promise<void> {
  await fetch(`/sessions/${encodeURIComponent(sessionId)}`, { method: 'DELETE' });
}

export async function health(): Promise<boolean> {
  try {
    const res = await fetch('/health');
    return res.ok;
  } catch {
    return false;
  }
}

export async function waitForJob(jobId: string, intervalMs = 600): Promise<ChatResponse> {
  for (;;) {
    await new Promise((r) => setTimeout(r, intervalMs));
    try {
      const job = await pollJob(jobId);
      if (job.status === 'success' && job.result) return job.result;
      if (job.status === 'failure') throw new Error(job.error ?? 'Turn failed');
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) continue;
      throw err;
    }
  }
}

export class QueuedResponse extends Error {
  readonly data: QueuedChatResponse;

  constructor(data: QueuedChatResponse) {
    super('queued');
    this.data = data;
  }
}

export interface StreamHandlers {
  onToken: (delta: string) => void;
  onDone: (data: ChatResponse) => void;
  onError: (message: string, status?: number) => void;
}

/**
 * POST /chat/stream and consume the SSE stream of chat-response tokens.
 *
 * Resolves when the `done` event arrives. Throws `QueuedResponse` when the
 * backend answers with 202 (queued processing mode) so the caller can fall
 * back to job polling. Calls `onError` (without throwing) for `error` events
 * or transport failures.
 */
export async function streamChat(
  message: string,
  sessionId: string | null,
  handlers: StreamHandlers,
): Promise<void> {
  let res: Response;
  try {
    res = await fetch('/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, session_id: sessionId }),
    });
  } catch (err) {
    handlers.onError(`Could not reach the server: ${err instanceof Error ? err.message : err}`);
    return;
  }

  if (res.status === 202) {
    throw new QueuedResponse(await json<QueuedChatResponse>(res));
  }
  if (!res.ok) {
    const data = (await res.json().catch(() => ({}))) as { detail?: string };
    handlers.onError(data.detail ?? `Request failed (${res.status})`, res.status);
    return;
  }

  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let gotDone = false;
  let errored = false;

  const handleLine = (line: string) => {
    const dataLine = line.split('\n').find((l) => l.startsWith('data:'));
    if (!dataLine) return;
    let payload: Record<string, unknown>;
    try {
      payload = JSON.parse(dataLine.slice(5).trim());
    } catch {
      return;
    }
    switch (payload.type) {
      case 'token':
        handlers.onToken(String(payload.content ?? ''));
        break;
      case 'done':
        gotDone = true;
        handlers.onDone(payload as unknown as ChatResponse);
        break;
      case 'error':
        errored = true;
        handlers.onError(String(payload.message ?? 'Turn failed'), Number(payload.status) || undefined);
        break;
    }
  };

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let idx: number;
    while ((idx = buffer.indexOf('\n\n')) >= 0) {
      handleLine(buffer.slice(0, idx));
      buffer = buffer.slice(idx + 2);
    }
  }
  buffer += decoder.decode();
  if (buffer.trim()) handleLine(buffer);

  if (!gotDone && !errored) {
    handlers.onError('Stream ended unexpectedly.');
  }
}