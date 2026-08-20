# MedGemma Agent — Milestone 6.2

Move chat-turn processing off the request/response cycle and onto a queue, so
inference runs in a dedicated Celery worker instead of inline inside the HTTP
request. Queued mode is optional (`PROCESSING_MODE=sync|queued`); sync remains
the default and its turn path is unchanged.

## What changed

### New module: `app/worker.py`

- **`celery`** — Celery app with `REDIS_URL` as both broker and result backend.
  Config: json serializers, `result_expires=JOB_RESULT_EXPIRE_SECONDS`,
  `worker_concurrency=JOB_CONCURRENCY` (default 1, fixed to match the
  single-GPU/VRAM constraint), `task_track_started=True`.
- **`TransientModelError`** — marker for retriable model-server failures
  (unreachable, timeout, `502`/`503`).
- **`JobProcessingError`** — marker for permanent (non-retriable) worker
  failures.
- **`process_turn` task** — `bind=True`, `autoretry_for=(TransientModelError,)`
  with `retry_backoff`, `retry_backoff_max=60`, `retry_jitter`, and
  `max_retries=JOB_MAX_RETRIES`. The body imports and runs the **same
  `run_chat_turn` path used by sync mode** inside `asyncio.run(...)` (fresh loop
  per task; the Redis/Postgres stores already create fresh connections per
  operation, so no loop-lifecycle management is needed). It maps:
  - `httpx.HTTPStatusError` with `502`/`503` → `TransientModelError` (retried)
  - `httpx.HTTPStatusError` with any other status → `JobProcessingError`
  - `httpx.ConnectError` / `httpx.TimeoutException` → `TransientModelError`
  - any other exception → `JobProcessingError`
  - success → `dataclasses.asdict(TurnResult)` (JSON-serializable; `Urgency` is
    a `str` subclass)
  - Error messages are prefixed `model-server-*` so the API can distinguish LLM
    failures from other failures when reading the stored result.

### New module: `app/jobs.py`

- Job registry backed by Redis: `mark_enqueued(job_id)` writes
  `medgemma:job:{job_id}` (TTL = `JOB_RESULT_EXPIRE_SECONDS`) and
  `exists(job_id)` checks it. This lets `GET /jobs/{job_id}` distinguish a job
  that exists but is still pending from one that never existed. A fresh Redis
  client per operation, mirroring `RedisSessionStore`.

### Changed: `app/core/config.py`

- **`.env` loading** — `python-dotenv`'s `load_dotenv()` runs before any
  `os.getenv`, so every setting now comes from `.env` (template:
  `.env.example`). Nothing is read from anywhere else.
- New settings: `PROCESSING_MODE` (`sync`), `JOB_RESULT_EXPIRE_SECONDS` (`3600`),
  `JOB_MAX_RETRIES` (`3`), `JOB_CONCURRENCY` (`1`).

### Changed: `app/services/chat.py`

- Emergency branch extracted into **`run_emergency_turn(message, *,
  session_id=None)`** — shared by sync mode and the queued-mode API, so the
  safety-floor short-circuit (session append + save + `safety_override` audit
  event) is byte-identical in both modes. `run_chat_turn` calls it for the
  emergency branch.

### Changed: `app/api/schemas.py`

- **`QueuedChatResponse`** — `job_id`, `session_id`, `status` (the `202` body).
- **`JobResponse`** — `job_id`, `status`, optional `result` (`ChatResponse`),
  optional `error`.

### Changed: `app/main.py`

- `POST /chat` now dispatches on `PROCESSING_MODE`:
  - **Sync** — unchanged path, returns the full `ChatResponse`.
  - **Queued** — the safety floor runs **synchronously first**; an emergency
    match short-circuits via `run_emergency_turn` and returns a full `200`
    response (never queued). Otherwise: new sessions are generated and
    pre-persisted so the returned `session_id` is the one the worker loads; a
    supplied `session_id` is validated (unknown/expired → `410`) before
    enqueue; the turn is enqueued via `process_turn.apply_async` and the job
    is marked in the registry; returns `202` `QueuedChatResponse`. A broker
    failure on send → `503`.
- **`GET /jobs/{job_id}`** — polls the Celery result backend:
  - unknown `job_id` (no result meta and no registry marker) → `404`
  - not ready → `200` `pending` / `processing`
  - success → `200` with the full `ChatResponse` result
  - failure with a `model-server-*` error (LLM failure, retries exhausted) →
    `200` with `status: "failure"` + error
  - failure for any other reason → `500`
- Lifespan fails fast with `RuntimeError` if `PROCESSING_MODE=queued` while
  `SESSION_STORE != redis`.

### Changed: `.env.example` / `requirements.txt` / `README.md`

- `.env.example` documents every env var (the single source of truth): the
  existing ones plus `PROCESSING_MODE`, `JOB_RESULT_EXPIRE_SECONDS`,
  `JOB_MAX_RETRIES`, `JOB_CONCURRENCY`.
- `requirements.txt` adds `celery` and `python-dotenv`; all direct deps are now
  pinned to exact versions.
- `README.md` rewritten for 6.2: queued-mode section (run commands, flow, job
  status table, retry policy, result TTL, out-of-scope), `GET /jobs` endpoint,
  `.env` loading note, full config table.

## Tests

- **`tests/test_worker.py`** (new, offline-safe):
  - queued `/chat` → `202` + `job_id`/`session_id`, `apply_async` receives the
    same args/temperature, job is marked
  - queued `/chat` emergency → `200` synchronous full response, never enqueued
  - queued `/chat` unknown `session_id` → `410`
  - `GET /jobs` mappings: unknown → `404`, `pending`, `processing`, `success`
    with result, LLM-failure → `200` failure, non-LLM failure → `500`
  - task body: calls `run_chat_turn` with the same args, maps `502`/`503`/
    connect/timeout → `TransientModelError`, passes through non-retriable HTTP
    statuses and non-LLM errors, and asserts the `autoretry_for`/backoff config
  - **live-Redis integration** (skipped when Redis is unreachable, same pattern
    as `test_postgres.py`): real Celery result backend round-trip — task runs
    (LLM mocked), result `mark_as_done`/`mark_as_failure` to Redis, job registry
    marker, then `GET /jobs` reads `success` and `failure` statuses from Redis.
- `test_settings_defaults` updated: `session_store_type` is now env-driven, and
  the new worker settings are asserted.

## Configuration

```text
PROCESSING_MODE=sync              # sync | queued (queued requires SESSION_STORE=redis)
JOB_RESULT_EXPIRE_SECONDS=3600    # TTL for Celery job results in Redis
JOB_MAX_RETRIES=3                 # retries for transient model-server failures
JOB_CONCURRENCY=1                 # worker concurrency (raise for multi-user; Ollama/VRAM is the real gate)
```

## Verification

- Full suite: 84 passed (64 previous + 20 new; the two live-Redis integration
  tests ran against `REDIS_URL` and were not skipped).
- `celery -A app.worker:celery report` loads cleanly; the `medgemma.process_turn`
  task is registered and the app reports `worker_concurrency=1`,
  `result_expires=3600`.

## Notes / trade-offs

- **Same turn path in both modes** — the worker task calls `run_chat_turn`, so
  safety/triage/routing/audit behavior is identical to sync mode. The safety
  floor additionally runs synchronously in the API before enqueue so the
  emergency short-circuit never depends on the queue.
- **New sessions are pre-created in Redis before enqueue** so the `session_id`
  in the `202` is the one the worker loads; otherwise the ids would diverge.
- **`asyncio.run` per task** = one fresh event loop per turn; safe because the
  stores use fresh connections per operation and concurrency defaults to 1. The
  in-process per-session `asyncio.Lock` does not span worker processes —
  cross-process session locking is a pre-existing gap, not introduced here.
- **Failure classification** uses message prefixes (`model-server-*`) because
  Celery's JSON result backend stores the exception's string form; the task
  controls the prefix so classification is reliable.
- **`apply_async` blocks the event loop briefly** on broker send (fast on local
  Redis); not offloaded to a threadpool.
- Job results in Redis are short-lived (`result_expires`); the append-only
  Postgres audit trail remains the durable record and is written by the same
  turn path.
- `JOB_CONCURRENCY` is configurable (default 1) — raising it lets multiple turns
  hit Ollama in parallel; Ollama's GPU/VRAM is the real ceiling.

## Out of scope (this milestone)

- Dead-letter queue
- Push/websocket notification on completion
- Concurrency above `JOB_CONCURRENCY` (reserved for a future multi-backend /
  remote-orchestration setup)