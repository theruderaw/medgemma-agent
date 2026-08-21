import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.sessions import InMemorySessionStore, SessionManager
from app.worker import (
    JobProcessingError,
    TransientModelError,
    process_turn,
)

client = TestClient(app)

CHAT_URL = "/v1/chat"


def _redis_available() -> bool:
    try:
        import redis.asyncio as aioredis

        async def probe() -> bool:
            redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
            try:
                return await redis_client.ping()
            finally:
                await redis_client.aclose()

        return asyncio.run(probe())
    except Exception:
        return False


class FakeAsyncResult:
    def __init__(
        self,
        *,
        meta,
        ready,
        successful,
        state="SUCCESS",
        result=None,
    ) -> None:
        self.backend = SimpleNamespace(get_task_meta=lambda job_id: meta)
        self._ready = ready
        self._successful = successful
        self.state = state
        self.result = result

    def ready(self):
        return self._ready

    def successful(self):
        return self._successful


def _patch_async_result(monkeypatch, fake: FakeAsyncResult) -> None:
    monkeypatch.setattr("app.main.process_turn.AsyncResult", lambda job_id: fake)

    async def fake_job_exists(job_id):
        return True

    monkeypatch.setattr("app.main.job_exists", fake_job_exists)


# ---------------------------------------------------------------------------
# POST /chat in queued mode
# ---------------------------------------------------------------------------


def test_queued_chat_returns_202_with_job_id(monkeypatch):
    monkeypatch.setattr(settings, "processing_mode", "queued")

    sent = {}

    def fake_apply_async(*, args, kwargs):
        sent["args"] = args
        sent["kwargs"] = kwargs
        return SimpleNamespace(id="job-123")

    async def fake_mark(job_id):
        sent["marked"] = job_id

    monkeypatch.setattr("app.main.process_turn.apply_async", fake_apply_async)
    monkeypatch.setattr("app.main.mark_enqueued", fake_mark)

    response = client.post(CHAT_URL, json={"message": "hello"})
    assert response.status_code == 202
    body = response.json()
    assert body["job_id"] == "job-123"
    assert body["status"] == "queued"
    assert body["session_id"]
    assert sent["args"] == ["hello"]
    assert sent["kwargs"]["session_id"] == body["session_id"]
    assert sent["kwargs"]["temperature"] == 0.7
    assert sent["kwargs"]["image_b64"] is None
    assert sent["kwargs"]["image_sha256"] is None
    assert sent["kwargs"]["image_size_bytes"] is None
    assert sent["marked"] == "job-123"


def test_queued_chat_emergency_short_circuits_sync(monkeypatch):
    monkeypatch.setattr(settings, "processing_mode", "queued")

    called = {"enqueue": False}

    def fake_apply_async(*, args, kwargs):
        called["enqueue"] = True
        return SimpleNamespace(id="x")

    monkeypatch.setattr("app.main.process_turn.apply_async", fake_apply_async)

    response = client.post(CHAT_URL, json={"message": "I have chest pain"})
    assert response.status_code == 200
    body = response.json()
    assert "medical emergency" in body["response"]
    assert body["urgency"] == "emergency"
    assert body["session_id"]
    assert called["enqueue"] is False


def test_queued_chat_unknown_session_returns_410(monkeypatch):
    monkeypatch.setattr(settings, "processing_mode", "queued")
    response = client.post(CHAT_URL, json={"message": "hi", "session_id": "unknown-session"})
    assert response.status_code == 410


def test_queued_chat_rejects_empty_message():
    response = client.post(CHAT_URL, json={"message": ""})
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# GET /jobs/{job_id}
# ---------------------------------------------------------------------------


def test_job_status_unknown_job_returns_404(monkeypatch):
    monkeypatch.setattr("app.main.process_turn.AsyncResult", lambda job_id: FakeAsyncResult(meta=None, ready=False, successful=False, state="PENDING"))

    async def fake_job_exists(job_id):
        return False

    monkeypatch.setattr("app.main.job_exists", fake_job_exists)
    assert client.get("/v1/jobs/never-existed").status_code == 404


def test_job_status_pending(monkeypatch):
    _patch_async_result(
        monkeypatch,
        FakeAsyncResult(meta={"status": "PENDING"}, ready=False, successful=False, state="PENDING"),
    )
    response = client.get("/v1/jobs/j1")
    assert response.status_code == 200
    assert response.json()["status"] == "pending"


def test_job_status_processing(monkeypatch):
    _patch_async_result(
        monkeypatch,
        FakeAsyncResult(meta={"status": "STARTED"}, ready=False, successful=False, state="STARTED"),
    )
    response = client.get("/v1/jobs/j1")
    assert response.status_code == 200
    assert response.json()["status"] == "processing"


def test_job_status_success(monkeypatch):
    _patch_async_result(
        monkeypatch,
        FakeAsyncResult(
            meta={"status": "SUCCESS"},
            ready=True,
            successful=True,
            result={
                "session_id": "s1",
                "response": "all good",
                "urgency": "routine",
                "events": [],
            },
        ),
    )
    response = client.get("/v1/jobs/j1")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["result"]["response"] == "all good"
    assert body["result"]["session_id"] == "s1"
    assert body["result"]["urgency"] == "routine"


def test_job_status_llm_failure_returns_200(monkeypatch):
    _patch_async_result(
        monkeypatch,
        FakeAsyncResult(
            meta={"status": "FAILURE"},
            ready=True,
            successful=False,
            state="FAILURE",
            result=JobProcessingError("model-server-http:502"),
        ),
    )
    response = client.get("/v1/jobs/j1")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failure"
    assert "model-server-http:502" in body["error"]


def test_job_status_non_llm_failure_returns_500(monkeypatch):
    _patch_async_result(
        monkeypatch,
        FakeAsyncResult(
            meta={"status": "FAILURE"},
            ready=True,
            successful=False,
            state="FAILURE",
            result=JobProcessingError("SessionExpiredError: session gone"),
        ),
    )
    response = client.get("/v1/jobs/j1")
    assert response.status_code == 500


# ---------------------------------------------------------------------------
# GET /jobs/{job_id}/events (SSE)
# ---------------------------------------------------------------------------


def test_job_events_unknown_job_returns_404(monkeypatch):
    monkeypatch.setattr(
        "app.main.process_turn.AsyncResult",
        lambda job_id: FakeAsyncResult(meta=None, ready=False, successful=False, state="PENDING"),
    )

    async def fake_job_exists(job_id):
        return False

    monkeypatch.setattr("app.main.job_exists", fake_job_exists)
    assert client.get("/v1/jobs/never-existed/events").status_code == 404


def test_job_events_streams_pipeline_then_result(monkeypatch):
    _patch_async_result(
        monkeypatch,
        FakeAsyncResult(
            meta={"status": "SUCCESS"},
            ready=True,
            successful=True,
            state="SUCCESS",
            result={
                "session_id": "s1",
                "response": "all good",
                "urgency": "routine",
                "events": [],
            },
        ),
    )

    async def fake_read_events(job_id, start=0):
        return [
            json.dumps(
                {
                    "module": "triage",
                    "event_type": "triage_result",
                    "payload": {"urgency": "routine"},
                    "turn_id": "t1",
                }
            )
        ], 1

    monkeypatch.setattr("app.main.read_events", fake_read_events)

    response = client.get("/v1/jobs/j1/events")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    text = response.text
    assert "event: pipeline" in text
    assert "triage_result" in text
    assert text.index("event: pipeline") < text.index("event: result")
    assert "all good" in text


def test_job_events_emits_error_on_failure(monkeypatch):
    _patch_async_result(
        monkeypatch,
        FakeAsyncResult(
            meta={"status": "FAILURE"},
            ready=True,
            successful=False,
            state="FAILURE",
            result=JobProcessingError("model-server-http:502"),
        ),
    )

    async def fake_read_events(job_id, start=0):
        return [], 0

    monkeypatch.setattr("app.main.read_events", fake_read_events)

    response = client.get("/v1/jobs/j1/events")
    assert response.status_code == 200
    assert "event: error" in response.text
    assert "model-server-http:502" in response.text


# ---------------------------------------------------------------------------
# Task body: same turn path + retry/error classification
# ---------------------------------------------------------------------------


def _memory_manager() -> SessionManager:
    return SessionManager(
        InMemorySessionStore(60),
        max_history_messages=40,
        max_context_messages=20,
        max_context_chars=16000,
    )


def _http_status(status: int) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "http://ollama")
    response = httpx.Response(status, request=request)
    return httpx.HTTPStatusError("model error", request=request, response=response)


def test_task_calls_run_chat_turn_with_same_args(monkeypatch):
    captured = {}

    async def fake_run(message, *, session_id=None, temperature=0.7, image=None, on_event=None):
        captured["message"] = message
        captured["session_id"] = session_id
        captured["temperature"] = temperature
        captured["on_event"] = on_event
        from app.services.chat import TurnResult

        return TurnResult(
            session_id=session_id or "s",
            response="ok",
            urgency="routine",
            events=[{"module": "chat", "event_type": "turn_completed", "payload": {}}],
        )

    monkeypatch.setattr("app.services.chat.run_chat_turn", fake_run)

    result = process_turn("hi", session_id="s", temperature=0.5)
    assert captured["message"] == "hi"
    assert captured["session_id"] == "s"
    assert captured["temperature"] == 0.5
    assert callable(captured["on_event"])
    assert result == {
        "session_id": "s",
        "response": "ok",
        "urgency": "routine",
        "events": [{"module": "chat", "event_type": "turn_completed", "payload": {}}],
    }


def test_task_maps_502_to_transient_error(monkeypatch):
    async def fail(message, *, session_id=None, temperature=0.7, image=None, on_event=None):
        raise _http_status(502)

    monkeypatch.setattr("app.services.chat.run_chat_turn", fail)
    with pytest.raises(TransientModelError):
        process_turn("hi")


def test_task_maps_503_to_transient_error(monkeypatch):
    async def fail(message, *, session_id=None, temperature=0.7, image=None, on_event=None):
        raise _http_status(503)

    monkeypatch.setattr("app.services.chat.run_chat_turn", fail)
    with pytest.raises(TransientModelError):
        process_turn("hi")


def test_task_maps_connect_error_to_transient_error(monkeypatch):
    async def fail(message, *, session_id=None, temperature=0.7, image=None, on_event=None):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr("app.services.chat.run_chat_turn", fail)
    with pytest.raises(TransientModelError):
        process_turn("hi")


def test_task_maps_timeout_to_transient_error(monkeypatch):
    async def fail(message, *, session_id=None, temperature=0.7, image=None, on_event=None):
        raise httpx.ReadTimeout("timed out")

    monkeypatch.setattr("app.services.chat.run_chat_turn", fail)
    with pytest.raises(TransientModelError):
        process_turn("hi")


def test_task_passes_non_retriable_http_status(monkeypatch):
    async def fail(message, *, session_id=None, temperature=0.7, image=None, on_event=None):
        raise _http_status(400)

    monkeypatch.setattr("app.services.chat.run_chat_turn", fail)
    with pytest.raises(JobProcessingError) as excinfo:
        process_turn("hi")
    assert str(excinfo.value).startswith("model-server-http:400")


def test_task_wraps_non_llm_error(monkeypatch):
    async def fail(message, *, session_id=None, temperature=0.7, image=None, on_event=None):
        raise ValueError("boom")

    monkeypatch.setattr("app.services.chat.run_chat_turn", fail)
    with pytest.raises(JobProcessingError) as excinfo:
        process_turn("hi")
    assert "ValueError" in str(excinfo.value)


def test_task_autoretry_configuration():
    assert process_turn.autoretry_for == (TransientModelError,)
    assert process_turn.max_retries == settings.job_max_retries
    assert process_turn.retry_backoff is True
    assert process_turn.retry_jitter is True


# ---------------------------------------------------------------------------
# Event publishing (SSE feed)
# ---------------------------------------------------------------------------


def test_run_chat_turn_invokes_on_event_per_recorded_event(monkeypatch):
    from app.audit import NullAuditLogger
    from app.llm import ChatResult

    monkeypatch.setattr("app.services.chat.sessions", _memory_manager())
    monkeypatch.setattr("app.services.chat.audit", NullAuditLogger())

    async def fake_triage(message, temperature=0.0, image_b64=None):
        return '{"urgency": "urgent"}'

    async def fake_route(messages, tools, temperature=0.7, model=None):
        return ChatResult(content="direct reply", tool_calls=[])

    monkeypatch.setattr("app.services.chat.llm.triage", fake_triage)
    monkeypatch.setattr("app.services.chat.llm.chat_with_tools", fake_route)

    from app.services.chat import run_chat_turn

    published = []

    async def on_event(event):
        published.append(event)

    result = asyncio.run(run_chat_turn("hi", on_event=on_event))

    assert [e["event_type"] for e in published] == ["triage_result", "routing_decision", "turn_completed"]
    assert result.events == published


def test_task_publishes_events_to_buffer(monkeypatch):
    published = []
    cleared = []

    async def fake_append(job_id, event):
        published.append((job_id, event))

    async def fake_clear(job_id):
        cleared.append(job_id)

    monkeypatch.setattr("app.worker.append_event", fake_append)
    monkeypatch.setattr("app.worker.clear_events", fake_clear)

    async def fake_run(message, *, session_id=None, temperature=0.7, image=None, on_event=None):
        await on_event(
            {
                "module": "triage",
                "event_type": "triage_result",
                "payload": {"urgency": "routine"},
                "turn_id": "t1",
            }
        )
        from app.services.chat import TurnResult

        return TurnResult(session_id="s", response="ok", urgency="general", events=[])

    monkeypatch.setattr("app.services.chat.run_chat_turn", fake_run)

    result = process_turn("hi", session_id="s", temperature=0.7)
    assert result["response"] == "ok"
    assert len(cleared) == 1
    assert published[0][0] == cleared[0]
    assert published[0][1]["event_type"] == "triage_result"


# ---------------------------------------------------------------------------
# Integration against live Redis (skipped when unreachable)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _redis_available(), reason="Redis server not available")
def test_queued_job_lifecycle_against_redis(monkeypatch):
    from app.audit import NullAuditLogger
    from app.llm import ChatResult
    from app.jobs import JOB_KEY_PREFIX, mark_enqueued

    monkeypatch.setattr(settings, "processing_mode", "queued")
    monkeypatch.setattr("app.services.chat.sessions", _memory_manager())
    monkeypatch.setattr("app.services.chat.audit", NullAuditLogger())

    async def fake_triage(message, temperature=0.0, image_b64=None):
        return '{"urgency": "self_care"}'

    async def fake_route(messages, tools, temperature=0.7, model=None):
        return ChatResult(content="hello from worker", tool_calls=[])

    monkeypatch.setattr("app.services.chat.llm.triage", fake_triage)
    monkeypatch.setattr("app.services.chat.llm.chat_with_tools", fake_route)

    try:
        eager = process_turn.apply(args=["hello"], kwargs={})
        job_id = eager.id
        assert eager.result["response"] == "hello from worker"
        process_turn.backend.mark_as_done(job_id, eager.result)
        asyncio.run(mark_enqueued(job_id))

        response = client.get(f"/v1/jobs/{job_id}")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "success"
        assert body["result"]["response"] == "hello from worker"
        assert body["result"]["session_id"]
        assert body["result"]["urgency"] == "self_care"
    finally:
        process_turn.backend.delete(job_id)
        import redis

        r = redis.Redis.from_url(settings.redis_url)
        r.delete(JOB_KEY_PREFIX + job_id)
        r.close()


@pytest.mark.skipif(not _redis_available(), reason="Redis server not available")
def test_queued_job_llm_failure_against_redis(monkeypatch):
    from app.audit import NullAuditLogger
    from app.jobs import JOB_KEY_PREFIX, mark_enqueued

    monkeypatch.setattr(settings, "processing_mode", "queued")
    monkeypatch.setattr("app.services.chat.sessions", _memory_manager())
    monkeypatch.setattr("app.services.chat.audit", NullAuditLogger())

    async def fail(message, *, session_id=None, temperature=0.7, image=None, on_event=None):
        raise _http_status(502)

    monkeypatch.setattr("app.services.chat.run_chat_turn", fail)

    try:
        eager = process_turn.apply(args=["hello"], kwargs={}, throw=False)
        job_id = eager.id
        assert eager.state == "FAILURE"
        assert "model-server-http:502" in str(eager.result)
        process_turn.backend.mark_as_failure(job_id, eager.result)
        asyncio.run(mark_enqueued(job_id))

        response = client.get(f"/v1/jobs/{job_id}")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "failure"
        assert "model-server-http:502" in body["error"]
    finally:
        process_turn.backend.delete(job_id)
        import redis

        r = redis.Redis.from_url(settings.redis_url)
        r.delete(JOB_KEY_PREFIX + job_id)
        r.close()