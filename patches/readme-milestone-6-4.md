# MedGemma Agent — Milestone 6.4

Structured logging and a hard audit guarantee: every log line is emitted through
structlog (pretty console + JSONL file), and **no transaction happens without an
explicit audit record appended to a JSON file** — regardless of `AUDIT_ENABLED`,
the session store, or processing mode. Long LLM-generated content is trimmed
before it lands in the audit trail.

## What changed

### Added: structlog everywhere (`app/core/logging.py`)

- **structlog 25.5.0** added to `requirements.txt`.
- `setup_logging()` now configures structlog end-to-end via
  `structlog.stdlib.ProcessorFormatter`:
  - console handler renders human-readably (`structlog.dev.ConsoleRenderer`)
  - file handler writes one JSON object per line to **`app/logs/app.jsonl`**
    (rotating, 5 MB x 3 backups, `JSONRenderer`)
  - uvicorn / celery / httpx foreign loggers flow through the same formatter
    (`foreign_pre_chain`), so framework noise is structured too
- **`get_logger(name)`** — returns a structlog bound logger; the app's standard
  `logging.getLogger(...)` and `print()` calls are gone.
- **Context variables** — `structlog.contextvars.bind_contextvars` merges
  `session_id` / `turn_id` / `job_id` into every line a turn or job emits; they
  are unbound when the turn/job ends.
- `app/llm/client.py` — the four `print(f"[llm] ...")` calls became structured
  events (`llm.chat`, `llm.chat_stream`, `llm.chat_with_tools`, `llm.triage`)
  carrying `model` + `temperature`.
- `app/main.py`, `app/worker.py`, `app/services/chat.py` — turn/job lifecycle
  events (`turn.started`, `event.recorded`, `turn.completed`, `job.started`,
  `job.enqueued`, `job.completed`, `job.failed`, `session.reset`,
  `job.stream.opened`, ...).

### Added: JSON-file audit trail (`app/audit/logger.py`)

The audit trail now **always** lands in an append-only JSONL file, independent
of Postgres:

- **`JsonFileAuditLogger`** — appends one JSON object per line to
  `AUDIT_FILE` (default `app/logs/audit.jsonl`). Append-only by construction:
  `O_APPEND` + a thread lock, never an update or delete. Writes run in
  `asyncio.to_thread` so the event loop is not blocked.
- **`CompositeAuditLogger`** — fans each event out to every configured sink.
  Sink failures are logged (`audit.sink_failed`) but never break the
  transaction, so a down Postgres can never lose the JSONL record.
- **`build_audit_logger()`** — returns a composite that **always** includes the
  JSONL file sink, and adds the `PostgresAuditLogger` when `AUDIT_ENABLED`
  (defaults on with `SESSION_STORE=postgres`). The `NullAuditLogger` default is
  gone — a `memory`/`redis` store no longer means "no audit".

### Added: LLM-content trimming

- **`trim_llm_payload(payload, cap)`** — deep-trims every string value in an
  audit payload to `AUDIT_LLM_CAP_CHARS` (default `1000`), appending
  `…[+N chars trimmed]`. Covers raw triage output, routing reasoning, tool-call
  arguments, specialist notes, and final replies — both nested lists/dicts and
  top-level strings.
- Applied at the source in `app/services/chat.py` (`record()` and the emergency
  path), `app/main.py` (`job_enqueued`), and `app/worker.py`
  (`job_completed`), and defensively again inside `JsonFileAuditLogger`, so the
  JSONL trail stays compact no matter which caller writes to it.

### Added: audit coverage for every transaction

Chat turns already audited `triage_result`, `routing_decision`,
`specialist_output`, `turn_completed`, and `safety_override`. 6.4 closes the
gaps so every transaction has an explicit record:

| Module | Event | When |
|---|---|---|
| `session` | `session_created` | New session pre-persisted in queued mode |
| `session` | `session_reset` | `DELETE /sessions/{id}` |
| `job` | `job_started` | Worker begins a turn |
| `job` | `job_enqueued` | `POST /chat` in queued mode |
| `job` | `job_completed` | Worker finished a turn |
| `job` | `job_failed` | Worker failed (retryable / permanent flagged) |

`app/worker.py` records these via `asyncio.run(...)` (the Celery task body is
synchronous and already runs the turn path in a fresh loop).

### Changed: `app/core/config.py`

- New settings: `AUDIT_FILE` (`app/logs/audit.jsonl`) and
  `AUDIT_LLM_CAP_CHARS` (`1000`), documented in `.env.example`.

## Tests

- **`tests/test_audit.py`** (new, offline-safe, 10 tests):
  - `JsonFileAuditLogger` appends exactly one JSON object per line, is
    append-only, and carries `timestamp` / `module` / `event_type` / `payload` /
    `session_id` / `turn_id`
  - trimming: long strings and nested `tool_calls` get the truncation marker,
    short values are untouched (`trim_llm_payload` recursion)
  - `CompositeAuditLogger` fans out to all sinks and swallows/logs sink failures
  - **no-transaction-without-audit integration** — a real chat turn, emergency
    short-circuit, session reset, and queued-mode enqueue each write their
    expected events to the JSONL file (audit logger monkeypatched to a temp file)
- Full suite: 99 passed (89 previous + 10 new).

## Configuration

```text
AUDIT_FILE=app/logs/audit.jsonl     # append-only JSONL audit trail (always written)
AUDIT_LLM_CAP_CHARS=1000            # trims LLM-generated content in audit records
```

## Verification

- Smoke-tested against a live Ollama server: a chat turn produced `triage_result`
  → `routing_decision` → `turn_completed` in `app/logs/audit.jsonl`, with the
  real audit singleton (`JsonFileAuditLogger` + `PostgresAuditLogger`);
  `DELETE /sessions/{id}` appended `session_reset`.
- `app/logs/app.jsonl` receives one JSON object per line for app, uvicorn,
  celery, and httpx events, with `session_id` / `turn_id` merged during turns.
- Full suite green: 99 passed.

## Notes / trade-offs

- **The JSONL file is the durable audit floor.** Postgres remains the
  structured queryable mirror when enabled, but a transaction is never silent:
  even a `memory`-store local run writes `audit.jsonl`.
- **Postgres payloads are no longer "retained in full".** 6.1 deliberately kept
  the MedGemma note verbatim for evaluation; the trimming cap now applies to all
  sinks for consistency (raise `AUDIT_LLM_CAP_CHARS` to relax). The live SSE /
  frontend events carry the same trimmed payloads.
- **Synchronous file I/O for audit appends** is offloaded via
  `asyncio.to_thread`; at one short line per event this is not a bottleneck.
- **`asyncio.run` per audit call in the worker** mirrors the existing
  `asyncio.run(run_chat_turn(...))` pattern — fresh loop per task, safe because
  stores create fresh connections per operation.
- Stale `contextvars` on a mid-turn exception are a cosmetic non-issue: each
  FastAPI request runs in its own task, and the worker unbinds on every path.

## Out of scope (this milestone)

- Queryable/structured log aggregation (JSONL is the format; shipping/ingestion
  is deployment-dependent).
- Encryption at rest / PII redaction of the audit file beyond length trimming.