import asyncio
import json
import logging

import httpx
from alembic import command
from alembic.config import Config
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .api import ChatRequest, ChatResponse, JobResponse, QueuedChatResponse
from .core.config import settings
from .core.logging import setup_logging
from .jobs import exists as job_exists
from .jobs import mark_enqueued
from .jobs import read_events
from .safety import detect_emergency
from .services.chat import run_chat_turn, run_chat_turn_stream, run_emergency_turn
from .sessions import SessionExpiredError, sessions
from .worker import process_turn

logger = logging.getLogger("app.main")

setup_logging()


def _run_migrations() -> None:
    cfg = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
    command.upgrade(cfg, "head")


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    if settings.processing_mode == "queued" and settings.session_store_type != "redis":
        raise RuntimeError("PROCESSING_MODE=queued requires SESSION_STORE=redis")
    if settings.session_store_type == "postgres" or settings.audit_enabled:
        await asyncio.to_thread(_run_migrations)
    yield
    await sessions.close()


app = FastAPI(title="MedGemma Agent", version="0.3.0", lifespan=lifespan)

app.mount("/static", StaticFiles(directory=Path(__file__).resolve().parent.parent / "static"), name="static")


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(Path(__file__).resolve().parent.parent / "static" / "index.html")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/chat")
async def chat(request: ChatRequest, response: Response):
    if settings.processing_mode == "queued":
        result = await queued_chat(request)
        if isinstance(result, QueuedChatResponse):
            response.status_code = 202
        return result
    return await sync_chat(request)


@app.post("/chat/stream")
async def chat_stream(request: ChatRequest, response: Response):
    """Server-Sent Events variant of `/chat` (sync mode).

    Streams the final reply token-by-token as ``event`/data` SSE messages:
    ``token`` events carry content deltas, a ``done`` event carries the full
    ChatResponse (session, urgency, events), and ``error`` events carry
    pipeline/model failures. In queued mode this falls back to `/chat`'s
    202 + job_id flow.
    """
    if settings.processing_mode == "queued":
        result = await queued_chat(request)
        if isinstance(result, QueuedChatResponse):
            response.status_code = 202
        return result
    return StreamingResponse(
        _stream_chat_turn(request),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _stream_chat_turn(request: ChatRequest):
    try:
        async for event in run_chat_turn_stream(
            request.message,
            session_id=request.session_id,
            temperature=request.temperature,
        ):
            yield f"data: {json.dumps(event)}\n\n"
    except SessionExpiredError:
        yield (
            "data: "
            + json.dumps(
                {
                    "type": "error",
                    "status": 410,
                    "message": "Session expired or not found. Start a new session.",
                }
            )
            + "\n\n"
        )
    except httpx.HTTPStatusError as exc:
        yield (
            "data: "
            + json.dumps(
                {"type": "error", "status": 502, "message": f"Model server error: {exc.response.status_code}"}
            )
            + "\n\n"
        )
    except httpx.HTTPError as exc:
        yield (
            "data: "
            + json.dumps({"type": "error", "status": 503, "message": f"Model server unreachable: {exc}"})
            + "\n\n"
        )
    except asyncio.CancelledError:
        logger.info("chat stream closed")
        raise


async def sync_chat(request: ChatRequest) -> ChatResponse:
    try:
        result = await run_chat_turn(
            request.message,
            session_id=request.session_id,
            temperature=request.temperature,
        )
    except SessionExpiredError:
        raise HTTPException(
            status_code=410,
            detail="Session expired or not found. Start a new session.",
        )
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"Model server error: {exc.response.status_code}")
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail=f"Model server unreachable: {exc}")
    return ChatResponse(
        session_id=result.session_id,
        response=result.response,
        urgency=result.urgency,
        events=result.events or [],
    )


async def queued_chat(request: ChatRequest) -> QueuedChatResponse | ChatResponse:
    """Queued-mode `/chat`.

    The deterministic safety floor runs synchronously first; an emergency match
    short-circuits with a full synchronous response and is never enqueued.
    Otherwise the turn is enqueued and a `202` with the Celery task id is
    returned; poll `GET /jobs/{job_id}` for the result.
    """
    if settings.triage_enabled and detect_emergency(request.message) is not None:
        result = await run_emergency_turn(request.message, session_id=request.session_id)
        return ChatResponse(
            session_id=result.session_id,
            response=result.response,
            urgency=result.urgency,
            events=result.events or [],
        )

    try:
        if request.session_id is None:
            session_id = sessions.new_id()
            session = await sessions.load_or_create(session_id, must_exist=False)
            await sessions.save(session)
        else:
            session_id = request.session_id
            await sessions.load_or_create(session_id, must_exist=True)

        task = process_turn.apply_async(
            args=[request.message],
            kwargs={"session_id": session_id, "temperature": request.temperature},
        )
        await mark_enqueued(task.id)
    except SessionExpiredError:
        raise HTTPException(
            status_code=410,
            detail="Session expired or not found. Start a new session.",
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Job queue unavailable: {exc}")

    return QueuedChatResponse(job_id=task.id, session_id=session_id, status="queued")


@app.get("/jobs/{job_id}", response_model=JobResponse)
async def job_status(job_id: str) -> JobResponse:
    result = process_turn.AsyncResult(job_id)
    meta = result.backend.get_task_meta(job_id)
    if meta is None and not await job_exists(job_id):
        raise HTTPException(status_code=404, detail="Job not found")

    if not result.ready():
        status = "processing" if result.state == "STARTED" else "pending"
        return JobResponse(job_id=job_id, status=status)

    if result.successful():
        return JobResponse(job_id=job_id, status="success", result=result.result)

    error = str(result.result) if result.result is not None else "unknown error"
    if error.startswith("model-server-"):
        return JobResponse(job_id=job_id, status="failure", error=error)
    raise HTTPException(status_code=500, detail=f"Job failed: {error}")


_JOB_EVENT_POLL_SECONDS = 0.5


@app.get("/jobs/{job_id}/events")
async def job_events_stream(job_id: str, request: Request) -> StreamingResponse:
    """Server-Sent Events stream for a queued job.

    Each pipeline event is streamed as an `event: pipeline` message as the
    worker produces it (replayed from the Redis buffer, so late or reconnecting
    clients never miss events). A final `event: result` or `event: error`
    message closes the stream once the Celery task finishes.
    """
    result = process_turn.AsyncResult(job_id)
    meta = result.backend.get_task_meta(job_id)
    if meta is None and not await job_exists(job_id):
        raise HTTPException(status_code=404, detail="Job not found")

    try:
        start = int(request.headers.get("last-event-id", "0") or "0")
    except ValueError:
        start = 0

    logger.info("job stream opened job=%s start=%s", job_id, start)
    return StreamingResponse(
        _stream_job_events(job_id, start=start),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _stream_job_events(job_id: str, *, start: int = 0):
    result = process_turn.AsyncResult(job_id)
    try:
        while True:
            items, length = await read_events(job_id, start)
            for i, raw in enumerate(items):
                yield f"id: {start + i}\nevent: pipeline\ndata: {raw}\n\n"
            start = length

            if result.ready():
                if result.successful():
                    logger.info("job stream done job=%s", job_id)
                    yield f"event: result\ndata: {json.dumps(result.result)}\n\n"
                else:
                    error = str(result.result) if result.result is not None else "unknown error"
                    logger.warning("job stream failed job=%s error=%s", job_id, error)
                    yield f"event: error\ndata: {json.dumps({'error': error})}\n\n"
                return

            await asyncio.sleep(_JOB_EVENT_POLL_SECONDS)
    except asyncio.CancelledError:
        logger.info("job stream closed job=%s", job_id)
        raise


@app.delete("/sessions/{session_id}", status_code=204)
async def reset_session(session_id: str) -> None:
    removed = await sessions.reset(session_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Session not found")