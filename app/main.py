import asyncio
import json
from uuid import uuid4

import httpx
from alembic import command
from alembic.config import Config
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .api import (
    ChatRequest,
    ChatResponse,
    ImageMeta,
    JobResponse,
    QueuedChatResponse,
    TriageRequest,
    TriageResponse,
)
from .audit import audit, trim_llm_payload
from .core.config import settings
from .core.images import ImageValidationError, ProcessedImage, decode_and_sanitize, persist_image
from .core.logging import get_logger, setup_logging
from .jobs import exists as job_exists
from .jobs import mark_enqueued
from .jobs import read_events
from .safety import detect_emergency
from .services.chat import run_chat_turn, run_chat_turn_stream, run_emergency_turn
from .services.triage import run_triage, triage_model_for
from .sessions import SessionExpiredError, sessions
from .triage import TriageResult, Urgency
from .worker import process_turn

logger = get_logger("app.main")

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


app = FastAPI(title="MedGemma Agent", version="0.4.0", lifespan=lifespan)

app.mount("/static", StaticFiles(directory=Path(__file__).resolve().parent.parent / "static"), name="static")


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(Path(__file__).resolve().parent.parent / "static" / "index.html")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


def _prepare_image(image_b64: str | None, image_mime: str | None) -> ProcessedImage | None:
    """Validate an optional upload into a sanitized ProcessedImage.

    Raises 422 when validation fails or only one of the two fields is given.
    """
    if image_b64 is None and image_mime is None:
        return None
    if image_b64 is None or image_mime is None:
        raise HTTPException(
            status_code=422,
            detail="image_b64 and image_mime must be provided together",
        )
    try:
        return decode_and_sanitize(image_b64, image_mime)
    except ImageValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


def _image_meta(image: ProcessedImage) -> ImageMeta:
    return ImageMeta(
        path=image.path or "",
        sha256=image.sha256,
        mime=image.mime,
        size_bytes=image.size_bytes,
    )


@app.post("/v1/triage", response_model=TriageResponse)
async def triage(request: TriageRequest) -> TriageResponse:
    """Stateless structured triage over text plus an optional image.

    Runs the deterministic red-flag floor first (a match short-circuits to a
    structured emergency result with no model calls), then dispatches to the
    tiny triage model for text-only turns or the multimodal MedGemma tier when
    an image is attached. Never mutates session state.
    """
    if not settings.triage_enabled:
        raise HTTPException(status_code=503, detail="Triage is disabled (TRIAGE_ENABLED=false)")

    turn_id = uuid4().hex
    image = _prepare_image(request.image_b64, request.image_mime)
    image_meta = None
    if image is not None:
        persist_image(image, turn_id)
        image_meta = _image_meta(image)
        await audit.append(
            module="image",
            event_type="image_received",
            payload={
                "path": image.path,
                "sha256": image.sha256,
                "mime": image.mime,
                "size_bytes": image.size_bytes,
            },
            turn_id=turn_id,
        )

    category = detect_emergency(request.message)
    if category is not None:
        result = TriageResult(
            urgency=Urgency.EMERGENCY,
            red_flags=[category],
            reasoning="Hardcoded red-flag rule matched; no model evaluation performed.",
        )
        await audit.append(
            module="safety",
            event_type="safety_override",
            payload={"category": category, "message": request.message},
            turn_id=turn_id,
        )
        logger.info("triage.completed", source="rules", urgency=result.urgency.value)
        return TriageResponse.from_result(result, model="hardcoded_rules", source="rules", image=image_meta)

    try:
        result = await run_triage(request.message, image_b64=image.b64 if image else None)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"Model server error: {exc.response.status_code}")
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail=f"Model server unreachable: {exc}")

    model = triage_model_for(image is not None)
    source = "vision" if image is not None else "text"
    await audit.append(
        module="triage",
        event_type="triage_result",
        payload=trim_llm_payload(
            {**result.to_dict(), "model": model, "source": source},
            settings.audit_llm_cap_chars,
        ),
        turn_id=turn_id,
    )
    logger.info("triage.completed", source=source, urgency=result.urgency.value)
    return TriageResponse.from_result(result, model=model, source=source, image=image_meta)


@app.post("/v1/chat")
async def chat(request: ChatRequest, response: Response):
    if settings.processing_mode == "queued":
        result = await queued_chat(request)
        if isinstance(result, QueuedChatResponse):
            response.status_code = 202
        return result
    return await sync_chat(request)


@app.post("/v1/chat/stream")
async def chat_stream(request: ChatRequest, response: Response):
    """Server-Sent Events variant of `/v1/chat` (sync mode).

    Streams the final reply token-by-token as ``event`/data` SSE messages:
    ``token`` events carry content deltas, a ``done`` event carries the full
    ChatResponse (session, urgency, events), and ``error`` events carry
    pipeline/model failures. In queued mode this falls back to `/v1/chat`'s
    202 + job_id flow.
    """
    if settings.processing_mode == "queued":
        result = await queued_chat(request)
        if isinstance(result, QueuedChatResponse):
            response.status_code = 202
        return result
    # Validate the upload before the stream opens so a 422 is a clean JSON
    # error rather than a mid-stream failure.
    image = _prepare_image(request.image_b64, request.image_mime)
    return StreamingResponse(
        _stream_chat_turn(request, image),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _stream_chat_turn(request: ChatRequest, image: ProcessedImage | None):
    try:
        async for event in run_chat_turn_stream(
            request.message,
            session_id=request.session_id,
            temperature=request.temperature,
            image=image,
        ):
            name = event.get("type", "message")
            yield f"event: {name}\ndata: {json.dumps(event)}\n\n"
    except SessionExpiredError:
        yield _sse_error(410, "Session expired or not found. Start a new session.")
    except httpx.HTTPStatusError as exc:
        yield _sse_error(502, f"Model server error: {exc.response.status_code}")
    except httpx.HTTPError as exc:
        yield _sse_error(503, f"Model server unreachable: {exc}")
    except asyncio.CancelledError:
        logger.info("chat.stream.closed")
        raise


def _sse_error(status: int, message: str) -> str:
    return (
        f"event: error\ndata: {json.dumps({'type': 'error', 'status': status, 'message': message})}\n\n"
    )


async def sync_chat(request: ChatRequest) -> ChatResponse:
    try:
        image = _prepare_image(request.image_b64, request.image_mime)
        result = await run_chat_turn(
            request.message,
            session_id=request.session_id,
            temperature=request.temperature,
            image=image,
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
    """Queued-mode `/v1/chat`.

    The deterministic safety floor runs synchronously first; an emergency match
    short-circuits with a full synchronous response and is never enqueued.
    Otherwise the turn is enqueued and a `202` with the Celery task id is
    returned; poll `GET /v1/jobs/{job_id}` for the result.
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
        image = _prepare_image(request.image_b64, request.image_mime)
        if request.session_id is None:
            session_id = sessions.new_id()
            session = await sessions.load_or_create(session_id, must_exist=False)
            await sessions.save(session)
            await audit.append(
                module="session",
                event_type="session_created",
                payload={"session_id": session_id},
                session_id=session_id,
            )
        else:
            session_id = request.session_id
            await sessions.load_or_create(session_id, must_exist=True)

        task = process_turn.apply_async(
            args=[request.message],
            kwargs={
                "session_id": session_id,
                "temperature": request.temperature,
                "image_b64": image.b64 if image else None,
                "image_sha256": image.sha256 if image else None,
                "image_size_bytes": image.size_bytes if image else None,
            },
        )
        await mark_enqueued(task.id)
        await audit.append(
            module="job",
            event_type="job_enqueued",
            payload=trim_llm_payload(
                {
                    "job_id": task.id,
                    "message": request.message,
                    "session_id": session_id,
                    "has_image": image is not None,
                },
                settings.audit_llm_cap_chars,
            ),
            session_id=session_id,
        )
        logger.info("job.enqueued", job_id=task.id, session_id=session_id, has_image=image is not None)
    except SessionExpiredError:
        raise HTTPException(
            status_code=410,
            detail="Session expired or not found. Start a new session.",
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Job queue unavailable: {exc}")

    return QueuedChatResponse(job_id=task.id, session_id=session_id, status="queued")


@app.get("/v1/jobs/{job_id}", response_model=JobResponse)
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


@app.get("/v1/jobs/{job_id}/events")
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

    logger.info("job.stream.opened", job_id=job_id, start=start)
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
                    logger.info("job.stream.done", job_id=job_id)
                    yield f"event: result\ndata: {json.dumps(result.result)}\n\n"
                else:
                    error = str(result.result) if result.result is not None else "unknown error"
                    logger.warning("job.stream.failed", job_id=job_id, error=error)
                    yield f"event: error\ndata: {json.dumps({'error': error})}\n\n"
                return

            await asyncio.sleep(_JOB_EVENT_POLL_SECONDS)
    except asyncio.CancelledError:
        logger.info("job.stream.closed", job_id=job_id)
        raise


@app.delete("/v1/sessions/{session_id}", status_code=204)
async def reset_session(session_id: str) -> None:
    removed = await sessions.reset(session_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Session not found")
    await audit.append(
        module="session",
        event_type="session_reset",
        payload={"session_id": session_id},
        session_id=session_id,
    )
    logger.info("session.reset", session_id=session_id)
