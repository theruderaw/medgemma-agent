import asyncio
from dataclasses import asdict

import httpx
import structlog
from celery import Celery

from .audit import audit, trim_llm_payload
from .bootstrap import bootstrap_addons
from .core.config import settings
from .core.logging import get_logger, setup_logging
from .jobs import append_event, clear_events

logger = get_logger("app.worker")

setup_logging()
bootstrap_addons()


class TransientModelError(Exception):
    """A model-server failure worth retrying: unreachable, timeout, 502/503."""


class JobProcessingError(Exception):
    """A permanent failure inside the worker that is not worth retrying."""


def _model_server_error(exc: Exception) -> str:
    """A message prefixed `model-server-` so the API can classify LLM failures.

    The upstream body excerpt is included: Ollama's error JSON names the real
    problem (unsupported feature, unknown model), which a bare status code
    discards.
    """
    if isinstance(exc, httpx.HTTPStatusError):
        return (
            f"model-server-http:{exc.response.status_code}:"
            f" {exc.response.text[:300]}"
        )
    return f"model-server-transport:{type(exc).__name__}"


celery = Celery(
    "medgemma",
    broker=settings.redis_url,
    backend=settings.redis_url,
)
celery.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    result_expires=settings.job_result_expire_seconds,
    worker_concurrency=settings.job_concurrency,
    task_track_started=True,
    task_ignore_result=False,
)


@celery.task(
    bind=True,
    name="medgemma.process_turn",
    autoretry_for=(TransientModelError,),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
    max_retries=settings.job_max_retries,
)
def process_turn(
    self,
    message: str,
    session_id: str | None = None,
    temperature: float = settings.temperature,
    image_b64: str | None = None,
    image_sha256: str | None = None,
    image_size_bytes: int | None = None,
    image_source_pages: int | None = None,
    triage: bool = False,
    slash_addon: str | None = None,
):
    """Run one full chat turn off the HTTP request path.

    Calls the same turn-processing path as the API so safety, triage,
    routing, and audit behavior are identical. ``image_b64`` arrives already
    sanitized by the API layer (validated, EXIF-stripped, downscaled); only
    the hash/size metadata rides alongside it. ``image_source_pages`` is the
    source document's page count for PDF uploads (None for images).
    ``triage`` is the per-turn opt-in from the ``?triage=true`` query param
    (off by default). Retries only transient model-server failures
    (unreachable, timeout, 502/503); all other errors propagate as a
    permanent task failure.
    """
    from .chat.turn import run_chat_turn
    from .core.images import ProcessedImage

    job_id = self.request.id

    image = None
    if image_b64 is not None:
        image = ProcessedImage(
            b64=image_b64,
            mime="image/jpeg",
            size_bytes=image_size_bytes or 0,
            sha256=image_sha256 or "",
            source_pages=image_source_pages,
        )

    structlog.contextvars.bind_contextvars(job_id=job_id, session_id=session_id)
    logger.info(
        "job.started",
        job_id=job_id,
        session_id=session_id,
        has_image=image is not None,
        triage=triage,
    )
    asyncio.run(
        audit.append(
            module="job",
            event_type="job_started",
            payload={"job_id": job_id, "message": message},
            session_id=session_id,
        )
    )

    try:
        asyncio.run(clear_events(job_id))
    except Exception:
        pass

    async def on_event(event: dict) -> None:
        try:
            await append_event(job_id, event)
        except Exception:
            pass

    async def on_token(content: str) -> None:
        try:
            await append_event(job_id, {"type": "token", "content": content})
        except Exception:
            pass

    async def on_specialist_token(content: str) -> None:
        try:
            await append_event(job_id, {"type": "specialist_token", "content": content})
        except Exception:
            pass

    async def on_structured(payload: dict) -> None:
        try:
            # A named SSE frame (event: structured) carrying the addon's
            # structured artifact so the UI can render it as its own card
            # while synthesis is still streaming.
            await append_event(job_id, {"type": "structured", **payload})
        except Exception:
            pass

    try:
        result = asyncio.run(
            run_chat_turn(
                message,
                session_id=session_id,
                temperature=temperature,
                image=image,
                triage=triage,
                slash_addon=slash_addon,
                on_event=on_event,
                on_token=on_token,
                on_specialist_token=on_specialist_token,
                on_structured=on_structured,
            )
        )
    except (httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException) as exc:
        if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code not in (502, 503):
            logger.warning("job.failed.permanent", job_id=job_id, error=_model_server_error(exc))
            asyncio.run(
                audit.append(
                    module="job",
                    event_type="job_failed",
                    payload={"job_id": job_id, "error": _model_server_error(exc), "retryable": False},
                    session_id=session_id,
                )
            )
            structlog.contextvars.unbind_contextvars("job_id", "session_id")
            raise JobProcessingError(_model_server_error(exc)) from exc
        logger.warning("job.failed.retryable", job_id=job_id, error=_model_server_error(exc))
        asyncio.run(
            audit.append(
                module="job",
                event_type="job_failed",
                payload={"job_id": job_id, "error": _model_server_error(exc), "retryable": True},
                session_id=session_id,
            )
        )
        structlog.contextvars.unbind_contextvars("job_id", "session_id")
        raise TransientModelError(_model_server_error(exc)) from exc
    except Exception as exc:
        logger.error("job.failed", job_id=job_id, error=repr(exc))
        asyncio.run(
            audit.append(
                module="job",
                event_type="job_failed",
                payload={"job_id": job_id, "error": f"{type(exc).__name__}: {exc}", "retryable": False},
                session_id=session_id,
            )
        )
        structlog.contextvars.unbind_contextvars("job_id", "session_id")
        raise JobProcessingError(f"{type(exc).__name__}: {exc}") from exc

    asyncio.run(
        audit.append(
            module="job",
            event_type="job_completed",
            payload=trim_llm_payload(
                {"job_id": job_id, "response": result.response, "session_id": result.session_id},
                settings.audit_llm_cap_chars,
            ),
            session_id=result.session_id,
        )
    )
    logger.info("job.completed", job_id=job_id, session_id=result.session_id, urgency=result.urgency)
    structlog.contextvars.unbind_contextvars("job_id", "session_id")
    return asdict(result)
