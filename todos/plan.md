# Plan — Next Milestones

Surface-level plan. Details live in `architecture.md` per milestone.

## 1. PostgreSQL (persistent storage)

- Replace in-memory/Redis session storage with PostgreSQL.
- Tables: sessions, messages, specialist outputs, routing decisions, safety
  overrides, triage results, execution metadata.
- Keep audit records append-only (e.g. `INSERT`-only for audit tables).
- Use SQLAlchemy async (or asyncpg directly) to stay on the existing asyncio
  stack; add a `SessionStore` implementation backed by Postgres.
- Add docker-compose or env-var-driven `DATABASE_URL`; migrations via Alembic.

## 2. Celery worker management

- Move slow/blocking work (triage, specialist, synthesis) out of the request
  path into a Celery worker so FastAPI stays responsive.
- New `POST /chat` flow: enqueue a task, return `202` + a task/status id;
  client polls or the UI reads status on completion.
- Redis remains the Celery broker (already available locally).
- Define task signatures per pipeline stage (triage → route → specialist →
  synthesis) so stages can be retried/observed independently.

## 3. React + Vite frontend

- Replace the single `index.html` chat page with a React app scaffolded via
  Vite (kept in a `web/` folder).
- Pages: chat, session list/reset, status/health; later an audit view.
- Talk to the FastAPI JSON API (same `/chat`, `/sessions/*` endpoints);
  handle the `202`/polling flow from the Celery milestone.
- Serve built assets from FastAPI (`StaticFiles`) or via Vite dev proxy to
  `localhost:8000` during development.

## 4. structlog (structured logging)
    
- Replace `print()` calls in `app/llm.py` (and any ad-hoc logging) with
  `structlog`.
- Bind context: request id, session id, model, turn id, routing decision,
  triage urgency, latencies.
- Emit JSON logs for the audit trail; integrate with the Python stdlib logging
  (uvicorn/access logs) so everything is structured.
- Sensitive fields (user message text) excluded or redacted by default.

## Suggested order

1. structlog (small, touches everything)
2. PostgreSQL (foundation for audit/state)
3. Celery (decouple the pipeline)
4. React + Vite (UI on top of the async API)