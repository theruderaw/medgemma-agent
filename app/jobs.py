"""Job registry helpers.

Queued-mode `/chat` marks a job as enqueued in Redis so `GET /jobs/{job_id}`
can distinguish a job that exists but is still pending from one that never
existed. The key is separate from the Celery result backend and expires with
the same TTL as the job result.
"""

import redis.asyncio as aioredis

from .core.config import settings

JOB_KEY_PREFIX = "medgemma:job:"


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