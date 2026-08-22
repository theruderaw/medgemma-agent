# MedGemma Agent — Milestone 8 (complete)

Milestone 8 — the **backend rework** — delivered as a single patch that made
Celery the only processing path, PostgreSQL the only session store, streaming
the only transport for every turn, and triage a per-turn opt-in. It also
rebuilt the frontend against the new contract and replaced the old mock-based
test suite with a spec-first integration suite that runs a real worker against
a fake Ollama server.

At the end of 8.x a client enqueues every turn (`202`), watches one SSE channel
(`GET /v1/jobs/{id}/events`) that streams the MedGemma clinical note and the
final reply token-by-token plus replayable pipeline events, and can read the
durable audit trail over HTTP. Nothing fundamental is configurable anymore:
behavior lives in code, configuration only tunes knobs.

---

## What changed

### Celery-only core

- **`app/main.py`** — `POST /v1/chat` always enqueues → `202 {job_id,
  session_id}`; the deterministic emergency floor still short-circuits
  synchronously (`200`, never queued). Deleted: sync chat path and
  `POST /v1/chat/stream`. The lifespan check tying queued mode to Redis
  sessions is gone; Alembic migrations run unconditionally at startup.
  New `_unknown_job()` fixes job 404s (Celery's `get_task_meta` returns a
  PENDING stub for unknown ids — the Redis enqueue marker is the oracle).
  Fixed: the enqueue error handler swallowed `HTTPException(422)`, making
  image-validation rejections unreachable.
- **`app/core/config.py`** — removed every behavior toggle:
  `TRIAGE_ENABLED`, `VISION_TRIAGE_MODEL_NAME`, `OUTPUT_GUARDRAILS`,
  `SESSION_STORE`, `AUDIT_ENABLED`, `PROCESSING_MODE`. Kept: models,
  timeouts, limits, URLs, job knobs.
- **Makefile** — non-blocking `api` / `worker` / `frontend` targets (pid +
  log files under `app/logs/`, double-start and port-conflict guards),
  `make up` starts the whole stack, `make stop` tears it down.

### Streaming everywhere

- **`app/llm/client.py`** — new `specialist_stream()`: Ollama native
  `/api/chat` with **both** `stream: true` and the `format` constraint, so
  MedGemma's structured JSON streams live without giving up schema
  enforcement. Blocking `specialist()` removed.
- **`app/services/chat.py`** — specialist deltas forward through
  `on_specialist_token` while accumulating the parseable JSON; synthesis
  streams via `on_token`. Deleted `run_chat_turn_stream`.
- **`app/worker.py`** — task forwards both callbacks into the replayable
  Redis event buffer as `{"type": "token"|"specialist_token", "content": …}`.
- **`app/main.py` `_stream_job_events`** — dispatches named SSE events
  (`pipeline | token | specialist_token | result | error`) with `id:` lines
  for `Last-Event-ID` replay, plus a final buffer flush before the terminal
  frame (task completion is ordered after all appends).
- **`app/services/chat.py`** — bug fix: `StreamExtractor.finish()`'s tail was
  appended to the stored reply but never forwarded through `on_token`,
  silently truncating streamed replies mid-word ("monitor your s").

### Triage opt-in + safety posture

- Triage is **off by default**; `?triage=true` opts in per turn. The
  classifier is now text-only `medgemma1.5:4b` — image bytes are held back
  from triage entirely and ride only to the specialist during analysis.
- Emergency floor and output guardrails are unconditional (guard skips its
  LLM call below `GUARD_MIN_CHARS` or without a triage urgency).

### Storage + audit

- **Sessions are PostgreSQL-only** — `InMemorySessionStore` /
  `RedisSessionStore` deleted; store contract moved to `sessions/base.py`;
  full history retained in storage (context caps apply only at send time).
- **Audit is always-on** — every event lands in the JSONL file *and* mirrors
  to Postgres `audit_events`; `NullAuditLogger` removed.
- **New endpoint** `GET /v1/audit?id=<session_id>&limit=N` — newest-first,
  read-only view of the durable trail.

### Reply sanitization

- **`app/llm/parsing.py`** — regression fix: when the function-calling router
  answers general questions inline, its meta-reasoning ("…should respond
  directly without triggering the specialist tool") used to surface verbatim
  as the user-visible reply. `extract_answer` now strips any preamble
  terminated by a `Response:` / `Answer:` / `Reply:` marker (case-insensitive,
  line-anchored so ordinary prose survives).

### Frontend

- Rewired against the new contract: `enqueueTurn()` (202-or-emergency-200)
  and `watchJob()` over a native `EventSource` with named-event listeners,
  automatic `Last-Event-ID` replay, and escalation to polling after repeated
  connection failures. Session id is captured from the `202` body immediately.
- Per-message **Triage toggle** in the composer (off by default).
- **Logs page** — Chat/Logs tabs; renders `/v1/audit` with module filter
  chips, session filter ("current session" one-click), expandable payload
  JSON, load-more pagination.
- Deleted the stale `static/index.html` prototype; `tsc && vite build` green.

## Diff from Milestone 7

| Contract | Milestone 7 | Milestone 8 |
|---|---|---|
| `POST /v1/chat` | Dual-mode: full response in sync mode, `202` in queued mode (`PROCESSING_MODE`) | Always `202` + `job_id` (`?triage=` opt-in); emergency floor alone returns `200` |
| `POST /v1/chat/stream` | SSE variant of chat (sync mode), `{type: …}` frames incl. `start`/`done` heartbeats | **Deleted** — replaced by `GET /v1/jobs/{id}/events` |
| `GET /v1/jobs/{id}/events` | Did not exist | Named SSE frames `pipeline/token/specialist_token/result/error`, replayable, token-streaming |
| Sessions | `memory` / `redis` / `postgres` stores behind `SESSION_STORE` | Postgres-only; full history retained |
| Audit sinks | JSONL always; Postgres mirror gated on `AUDIT_ENABLED` | Both unconditional |
| Triage | Always-on classifier, vision tier for images (`qwen3:0.6b` text / MedGemma vision), extended findings schema | Off by default, `?triage=true` opt-in, text-only `medgemma1.5:4b`, urgency-only schema |
| Guardrails | Gated on `OUTPUT_GUARDRAILS` | Always on (deterministic skip gate) |
| Env toggles | 6 behavior switches | None — knobs only |
| Unknown job id | Returned `pending` forever (PENDING stub) | `404` |
| Image validation errors | Masked as `503` by the enqueue handler | `422` |
| Job result payload | `ChatResponse` | + `path` (pipeline path taken) |
| Audit read API | File/DB only | `GET /v1/audit` |
| Frontend transport | POST stream + polling fallback | EventSource on job-events + polling last resort |
| Tests | ~140 offline unit tests, mocks, conditional skips | Spec-first integration suite: real Celery worker subprocess vs fake Ollama HTTP server, live Postgres/Redis required (fail-fast), isolated on Redis db 15 |

## Configuration

```text
MODEL_NAME=qwen3:4b
SPECIALIST_MODEL_NAME=medgemma1.5:4b
TRIAGE_MODEL_NAME=medgemma1.5:4b        # text-only triage
GUARD_MODEL_NAME=qwen3:0.6b
GUARD_MIN_CHARS=200
REDIS_URL=redis://localhost:6379/0      # broker/backend/event buffers
DATABASE_URL=postgresql:///medgemma-agent
JOB_RESULT_EXPIRE_SECONDS=3600
```

(Runbook: `make up` → API :8000, worker, UI :5173.)

## Verification

- Integration suite: **35 tests green in ~11 s** (`tests/integration`) —
  real Celery worker subprocess consuming the real Redis queue against an
  in-process fake Ollama HTTP server; live Postgres/Redis required (fail-fast,
  never skip); suite traffic isolated on Redis db 15 so it cannot collide with
  a running dev stack. Coverage: enqueue/completion flows, router decline,
  permanent-failure mapping, router-deliberation stripping (regression),
  triage opt-in semantics, emergency floor, guardrails, postgres session
  persistence/reset, image pipeline, standalone triage endpoint, audit read
  API, and the full job-events SSE contract including token streaming.
- Live smoke vs real Ollama: one turn streamed `pipeline → 99
  specialist_token → 32 token → result`; result `success` with
  `path=medical_specialist`; `/v1/audit?id=…` returned the trail newest-first.

## Trade-offs / out of scope

- Job lookups/events 404 after the Redis TTL expires — runs are ephemeral;
  the audit trail (and now `/v1/audit`) is the durable record.
- No dead-letter queue; concurrency capped by `JOB_CONCURRENCY` (GPU-bound).
- No auth layer yet; images remain metadata-only in the trail.
