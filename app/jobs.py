"""Job registry + event-buffer helpers.

Queued-mode `/chat` marks a job as enqueued in Redis so `GET /jobs/{job_id}`
can distinguish a job that exists but is still pending from one that never
existed. The key is separate from the Celery result backend and expires with
the same TTL as the job result.

The worker also appends each pipeline event to a per-job Redis list keyed by
`medgemma:job-events:{job_id}`. The SSE stream (`GET /jobs/{job_id}/events`)
drains that list incrementally, so events are replayed to late or reconnecting
subscribers instead of being lost between publish and subscribe.
"""

import json

import redis.asyncio as aioredis

from .core.config import settings

JOB_KEY_PREFIX = "medgemma:job:"
EVENT_KEY_PREFIX = "medgemma:job-events:"


def _client() -> aioredis.Redis:
    return aioredis.from_url(settings.redis_url, decode_responses=True)


async def mark_enqueued(job_id: str) -> None:
    client = _client()
    try:
        await client.set(
            JOB_KEY_PREFIX + job_id,
            "queued",
            ex=settings.job_result_expire_seconds,
        )
    finally:
        await client.aclose()


async def exists(job_id: str) -> bool:
    client = _client()
    try:
        return await client.exists(JOB_KEY_PREFIX + job_id) > 0
    finally:
        await client.aclose()


async def broker_ping() -> bool:
    """True when the Redis broker answers PING (used by GET /health)."""
    client = _client()
    try:
        return bool(await client.ping())
    except Exception:
        return False
    finally:
        await client.aclose()


async def append_event(job_id: str, event: dict) -> None:
    client = _client()
    try:
        key = EVENT_KEY_PREFIX + job_id
        pipe = client.pipeline()
        pipe.rpush(key, json.dumps(event))
        pipe.expire(key, settings.job_result_expire_seconds)
        await pipe.execute()
    finally:
        await client.aclose()


async def read_events(job_id: str, start: int = 0) -> tuple[list[str], int]:
    """Return events at index >= `start` along with the new list length."""
    client = _client()
    try:
        key = EVENT_KEY_PREFIX + job_id
        length = await client.llen(key)
        if start >= length:
            return [], length
        items = await client.lrange(key, start, length - 1)
        return items, length
    finally:
        await client.aclose()


async def clear_events(job_id: str) -> None:
    client = _client()
    try:
        await client.delete(EVENT_KEY_PREFIX + job_id)
    finally:
        await client.aclose()