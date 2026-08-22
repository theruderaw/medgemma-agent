# Rework: Celery-only · Postgres-only · All-chat-streamed

Status: **COMPLETE** — all three phases done; integration suite 28/28 green.
After each numbered task (and certainly each phase): pause, report what changed,
run the relevant tests, ask before continuing.

> Test strategy note (supersedes 1.6 / 2.4 / 3.5 as originally written):
> the old test suite was deleted; a fresh spec-first integration suite lives in
> `tests/integration/` and defines target behavior — including Phase-3 contracts
> that are still red until Phase 3 lands ("code should fit tests"). Infra:
> real Celery worker subprocess + fake Ollama HTTP server + live Postgres/Redis
> (fail-fast, never skip).

## Locked decisions

- Triage **off by default**; opt-in per request via `?triage=true` query param.
- Hardcoded safety floor (`detect_emergency`) is **always on**, independent of triage.
  No model call — emergencies short-circuit before anything else.
- Triage model = `medgemma1.5:4b`, text-only. Images are never sent to triage;
  they ride only to the specialist during analysis.
- Celery is the **only** processing path. Sync mode is deleted.
- All turns stream: raw MedGemma JSON deltas (`specialist_token`) + final reply
  deltas (`token`) through the existing `/v1/jobs/{id}/events` SSE.
- `/v1/chat` and `/v1/chat?triage=true` are identical client contracts (202 + SSE);
  triage only adds the `triage_result` pipeline event.
- Sessions/messages/audit → Postgres (SQLModel + asyncpg). Runs stay Redis-only
  (ephemeral, TTL'd) — `sessions` + `messages` + `audit_events` are the durable
  run history. Accepted gap: `job_id` lookups 404 after Redis TTL expiry.
- Frontend untouched ("develop later"). Alembic schema unchanged (no new tables).
- Env vars: keep models / timeouts / limits / URLs / job knobs; remove everything
  that hardcodes fundamental behavior.

## Phase 1 — Celery-only + triage opt-in + config cleanup

- [x] 1.1 `app/core/config.py` + `.env.example`
  - Remove: `TRIAGE_ENABLED`, `VISION_TRIAGE_MODEL_NAME`, `OUTPUT_GUARDRAILS`,
    `SESSION_STORE`, `AUDIT_ENABLED`, `PROCESSING_MODE`
  - Flip default: `TRIAGE_MODEL_NAME=medgemma1.5:4b`
  - Keep: `MODEL_NAME`, `SPECIALIST_MODEL_NAME`, `TRIAGE_MODEL_NAME`,
    `GUARD_MODEL_NAME`, `GUARD_MIN_CHARS`, image limits, `OLLAMA_BASE_URL`,
    `LLM_TIMEOUT_SECONDS`, `DATABASE_URL`, `REDIS_URL`,
    `SESSION_TIMEOUT_SECONDS`, `MAX_*`, `AUDIT_FILE`, `AUDIT_LLM_CAP_CHARS`,
    `JOB_RESULT_EXPIRE_SECONDS`, `JOB_MAX_RETRIES`, `JOB_CONCURRENCY`
- [x] 1.2 `app/services/chat.py`
  - `run_chat_turn(..., triage: bool = False)` replaces both
    `if settings.triage_enabled:` blocks
  - Emergency floor unconditional (runs every turn)
  - Output-guardrail gate removed — `run_output_guard` runs on every reply
    (setting was deleted in 1.1; fallout folded into this task)
  - Delete `run_chat_turn_stream` (job-events SSE replaces it)
- [x] 1.3 `app/main.py`
  - `/v1/chat`: always enqueue → `202 {job_id, session_id}`; pass `triage`
    query param into task kwargs; emergency match still returns 200 synchronously
  - Delete `sync_chat` and `/v1/chat/stream`
  - `/v1/triage`: remove `TRIAGE_ENABLED` 503 gate
  - Pre-enqueue emergency floor: drop `settings.triage_enabled` condition
  - Folded fallout from 1.1: lifespan redis/processing-mode check removed and
    migrations now run unconditionally (completes the code side of 2.2)
- [x] 1.4 `app/worker.py`
  - `process_turn(message, session_id, temperature, image_*, triage=False)`
    threads flag into `run_chat_turn`
- [x] 1.5 Runbook
  - `make worker` target (or documented command):
    `celery -A app.worker:celery worker --concurrency=1`
  - `/health` reports broker reachability (dead worker/broker visible)
  - Note: `app/jobs.py` was found accidentally moved to `tests/jobs.py`
    (broken relative import) mid-phase — restored from git, `broker_ping()`
    added there; stray `tests/jobs.py` pending deletion by Rudra
- [x] 1.6 Tests — **superseded** by the new spec-first integration suite
  (`tests/integration/`); old suite deleted by Rudra

## Phase 2 — Postgres-only sessions + audit always-on ✅

- [x] 2.1 `app/sessions/`
  - Deleted `stores.py` (InMemory + Redis stores) and `build_store()`;
    store ABC moved to `base.py`, singleton hardwired to
    `PostgresSessionStore(settings.database_url, settings.session_timeout_seconds)`
  - `sessions/__init__.py` exports trimmed; `_expired()` helper restored to the
    base class (suite caught its loss), `Session` import fixed in `postgres.py`
- [x] 2.2 `app/main.py` lifespan — done during 1.3: processing-mode check
  removed, migrations unconditional
- [x] 2.3 `app/audit/logger.py` — `build_audit_logger()` always returns the
  JSONL + Postgres composite; dead `NullAuditLogger` removed
- [x] 2.4 Test infrastructure — **superseded** by `tests/integration/`:
  fail-fast live-postgres probe, `create_all`, per-test truncate of
  sessions/messages/audit + Redis job keys, fake Ollama server, real worker subprocess

## Phase 3 — Stream all tokens ✅

- [x] 3.1 `app/llm/client.py`
  - Added `specialist_stream(messages, images, temperature, model)`:
    native `/api/chat`, `stream: true` **with** `format` constraint;
    yields raw deltas. Blocking `specialist()` removed (single caller converted).
- [x] 3.2 `app/services/chat.py`
  - Specialist stage consumes the stream: each delta → `on_specialist_token`;
    accumulated JSON → `parse_specialist_result` at completion
    (post-hoc 64-char chunking deleted)
- [x] 3.3 `app/worker.py`
  - `on_token` / `on_specialist_token` append
    `{"type": "token"|"specialist_token", "content": ...}` via `append_event`
- [x] 3.4 `app/main.py` `_stream_job_events`
  - Dispatches SSE name by payload `type`:
    `pipeline | token | specialist_token | result | error`; `id:` lines kept
    for Last-Event-ID replay; final buffer flush before the terminal event
    (task completion is ordered after all appends, one extra read suffices)
- [x] 3.5 Tests — suite green: **28 passed** (`tests/integration`, ~10s)
  - Suite caught a real bug here: `StreamExtractor.finish()` tail was appended
    to the accumulated reply but never forwarded through `on_token`

## Post-rework runbook

```
redis-server                                          # broker (already running)
postgres                                              # live DB medgemma-agent
celery -A app.worker:celery worker --concurrency=1    # REQUIRED for chat
uvicorn app.main:app --port 8000
```

## Notes

- Two redis-server processes were observed listening on 6379 (one user
  `redis`, one odd `dnsmasq`-labeled) — clean up so the broker is unambiguous.
- Worker process is mandatory once celery-only lands; API alone leaves jobs
  forever pending.
