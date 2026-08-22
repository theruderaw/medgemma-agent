"""Integration-suite infrastructure — spec-first.

These tests define the target behavior of the reworked system: celery-only
processing, postgres-only sessions, opt-in triage, streamed tokens. The code
must satisfy the tests, never the reverse.

Hermetic at the network boundary: a real Celery worker subprocess consumes
the real Redis broker queue, with every model call served by an in-process
fake Ollama HTTP server (no models downloaded, no Python-level mocks of app
code). Live PostgreSQL and Redis are required — a missing service fails the
suite loudly instead of skipping.

Import-order contract: this module starts the fake server and points
OLLAMA_BASE_URL at it BEFORE any ``app.llm`` import happens (test modules
are collected after conftest executes), so both the in-process API client
and the worker subprocess talk to the fake — never to a real Ollama.
"""

import asyncio
import base64
import io
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
import redis.asyncio as aioredis

from tests.integration.fake_ollama import FakeOllama

REPO_ROOT = Path(__file__).resolve().parents[2]

_FAKE_OLLAMA = FakeOllama()
_FAKE_OLLAMA.start()
os.environ["OLLAMA_BASE_URL"] = _FAKE_OLLAMA.base_url


def _isolate_redis() -> None:
    """Point the suite at a dedicated Redis DB (default 15).

    Without this, a concurrently running dev worker consumes the same broker
    queue and steals/executes test jobs against freshly-truncated Postgres
    rows — producing phantom failures. Must run before any app.core.config
    import bakes settings.
    """
    url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    base, _, db = url.rpartition("/")
    if db.isdigit():
        url = f"{base}/15"
    else:
        url = f"{url}/15"
    os.environ["REDIS_URL"] = url


_isolate_redis()

SPECIALIST_JSON = json.dumps(
    {
        "summary": "Possible mild irritation.",
        "findings": ["mild redness"],
        "visual_findings": [],
        "red_flag_concerns": [],
        "limitations": ["assessment limited to user text"],
        "uncertain": False,
    }
)


# ---------------------------------------------------------------------------
# Required services


def _postgres_ready() -> bool:
    from app.core.config import settings

    try:
        import asyncpg

        async def probe() -> bool:
            conn = await asyncpg.connect(settings.database_url)
            try:
                await conn.execute("SELECT 1")
                return True
            finally:
                await conn.close()

        return asyncio.run(probe())
    except Exception:
        return False


@pytest.fixture(scope="session", autouse=True)
def _require_live_services():
    if not _postgres_ready():
        pytest.exit(
            "Live PostgreSQL required (DATABASE_URL) — integration suite never skips",
            returncode=1,
        )


# ---------------------------------------------------------------------------
# Fake Ollama + real Celery worker


@pytest.fixture(scope="session")
def fake_ollama():
    yield _FAKE_OLLAMA


@pytest.fixture(scope="session")
def celery_worker(fake_ollama):
    """A genuine Celery worker process pointed at the fake model server."""
    env = {**os.environ, "OLLAMA_BASE_URL": fake_ollama.base_url}
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "celery",
            "-A",
            "app.worker.celery",
            "worker",
            "--pool=solo",
            "--concurrency=1",
            "-l",
            "warning",
            "--without-gossip",
            "--without-mingle",
            "--without-heartbeat",
        ],
        cwd=REPO_ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )
    from app.worker import celery as celery_app

    deadline = time.monotonic() + 30
    ready = False
    while time.monotonic() < deadline:
        try:
            if celery_app.control.inspect(timeout=0.5).ping():
                ready = True
                break
        except Exception:
            pass
        if proc.poll() is not None:
            pytest.exit(f"Celery worker died during startup (rc={proc.returncode})", returncode=1)
        time.sleep(0.3)
    if not ready:
        proc.terminate()
        pytest.exit("Celery worker never became ready within 30s", returncode=1)

    yield proc

    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture(scope="session", autouse=True)
def _schema(celery_worker):
    from app.core.db import create_all

    asyncio.run(create_all())


@pytest.fixture(autouse=True)
def _clean_stores(fake_ollama):
    """Fresh Postgres rows, Redis job keys, and fake-server state per test."""
    import asyncpg

    from app.core.config import settings
    from app.jobs import EVENT_KEY_PREFIX, JOB_KEY_PREFIX

    async def clean() -> None:
        conn = await asyncpg.connect(settings.database_url)
        try:
            await conn.execute(
                "TRUNCATE sessions, messages, audit_events RESTART IDENTITY CASCADE"
            )
        finally:
            await conn.close()
        client = aioredis.from_url(settings.redis_url, decode_responses=True)
        try:
            keys = [key async for key in client.scan_iter(f"{JOB_KEY_PREFIX}*")]
            keys += [key async for key in client.scan_iter(f"{EVENT_KEY_PREFIX}*")]
            if keys:
                await client.delete(*keys)
        finally:
            await client.aclose()

    asyncio.run(clean())
    fake_ollama.reset()
    yield


# ---------------------------------------------------------------------------
# HTTP / data helpers


@pytest.fixture
async def client(celery_worker):
    from app.main import app

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


@pytest.fixture
def tiny_png() -> str:
    """A valid 1x1 PNG upload as base64."""
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (1, 1), color=(200, 100, 100)).save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode()


async def db_fetch(query: str, *args) -> list[dict]:
    import asyncpg

    from app.core.config import settings

    conn = await asyncpg.connect(settings.database_url)
    try:
        rows = await conn.fetch(query, *args)
        return [dict(row) for row in rows]
    finally:
        await conn.close()


async def db_fetchone(query: str, *args) -> dict | None:
    rows = await db_fetch(query, *args)
    return rows[0] if rows else None


async def wait_for_job(client: httpx.AsyncClient, job_id: str, timeout: float = 15.0) -> dict:
    """Poll GET /jobs/{id} until the worker finishes; returns final body."""
    deadline = time.monotonic() + timeout
    body: dict = {}
    while time.monotonic() < deadline:
        response = await client.get(f"/v1/jobs/{job_id}")
        if response.status_code == 500:
            raise AssertionError(f"job {job_id} crashed the API: {response.json()}")
        body = response.json()
        if body.get("status") in ("success", "failure"):
            return body
        await asyncio.sleep(0.1)
    raise AssertionError(f"job {job_id} did not finish within {timeout}s: {body}")


async def drain_sse(client: httpx.AsyncClient, path: str) -> list[tuple[str, str]]:
    """Read an SSE stream to its terminating ``result``/``error`` event."""
    events: list[tuple[str, str]] = []
    async with asyncio.timeout(30):
        async with client.stream("GET", path) as response:
            response.raise_for_status()
            name = None
            async for line in response.aiter_lines():
                if line.startswith("event:"):
                    name = line.split(":", 1)[1].strip()
                elif line.startswith("data:") and name is not None:
                    events.append((name, line.split(":", 1)[1].strip()))
                    if name in ("result", "error"):
                        break
                    name = None
    return events
