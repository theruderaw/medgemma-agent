import asyncio
from dataclasses import asdict

import httpx
from celery import Celery

from .core.config import settings


class TransientModelError(Exception):
    """A model-server failure worth retrying: unreachable, timeout, 502/503."""


class JobProcessingError(Exception):
    """A permanent failure inside the worker that is not worth retrying."""


def _model_server_error(exc: Exception) -> str:
    """A message prefixed `model-server-` so the API can classify LLM failures."""
    if isinstance(exc, httpx.HTTPStatusError):
        return f"model-server-http:{exc.response.status_code}"
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
def process_turn(self, message: str, session_id: str | None = None, temperature: float = 0.7):
    """Run one full chat turn off the HTTP request path.

    Calls the same turn-processing path as sync mode so safety, triage,
    routing, and audit behavior are identical. Retries only transient
    model-server failures (unreachable, timeout, 502/503); all other errors
    propagate as a permanent task failure.
    """
    from .services.chat import run_chat_turn

    try:
        result = asyncio.run(
            run_chat_turn(message, session_id=session_id, temperature=temperature)
        )
    except (httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException) as exc:
        if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code not in (502, 503):
            raise JobProcessingError(_model_server_error(exc)) from exc
        raise TransientModelError(_model_server_error(exc)) from exc
    except Exception as exc:
        raise JobProcessingError(f"{type(exc).__name__}: {exc}") from exc
    return asdict(result)