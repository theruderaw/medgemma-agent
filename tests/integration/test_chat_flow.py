"""End-to-end chat turn flow: API enqueue → real Celery worker → persisted result."""

import pytest

from .conftest import wait_for_job

pytestmark = pytest.mark.asyncio


class TestChatEnqueue:
    async def test_chat_always_enqueues_202(self, client):
        response = await client.post("/v1/chat", json={"message": "my arm hurts"})
        assert response.status_code == 202
        body = response.json()
        assert body["status"] == "queued"
        assert body["job_id"]
        assert body["session_id"]

    async def test_enqueue_creates_session_row_in_postgres(self, client):
        from .conftest import db_fetchone

        session_id = (await client.post("/v1/chat", json={"message": "hi"})).json()["session_id"]
        row = await db_fetchone("SELECT session_id FROM sessions WHERE session_id = $1", session_id)
        assert row is not None

    async def test_unknown_session_rejected_410(self, client):
        response = await client.post(
            "/v1/chat", json={"message": "hi", "session_id": "does-not-exist"}
        )
        assert response.status_code == 410


class TestWorkerTurnCompletion:
    async def test_completed_turn_persists_reply_and_result(self, client):
        from .conftest import db_fetch

        body = (await client.post("/v1/chat", json={"message": "my arm hurts"})).json()
        payload = await wait_for_job(client, body["job_id"])
        assert payload["status"] == "success"

        result = payload["result"]
        assert result["session_id"] == body["session_id"]
        assert result["path"] == "medical_specialist"
        assert "monitor your symptoms" in result["response"]

        messages = await db_fetch(
            "SELECT role, content FROM messages WHERE session_id = $1 ORDER BY seq",
            body["session_id"],
        )
        roles = [m["role"] for m in messages]
        assert roles[0] == "user"
        assert "assistant" in roles

    async def test_router_declining_specialist_answers_directly(self, client, fake_ollama):
        fake_ollama.configure(router_mode="general")

        job_id = (await client.post("/v1/chat", json={"message": "what is water?"})).json()["job_id"]
        payload = await wait_for_job(client, job_id)
        assert payload["result"]["path"] == "qwen_direct"
        assert fake_ollama.calls("specialist") == []

    async def test_permanent_model_failure_maps_to_job_failure(self, client, fake_ollama):
        """A 500 from the model server after retries exhausts → FAILURE job.

        The retry policy lives on the Celery task; the queue round-trip is the
        contract under test here.
        """
        fake_ollama.fail_next_router_calls_with(500)

        job_id = (await client.post("/v1/chat", json={"message": "hi"})).json()["job_id"]
        payload = await wait_for_job(client, job_id, timeout=60.0)
        assert payload["status"] == "failure"

    async def test_router_deliberation_never_reaches_the_user(self, client, fake_ollama):
        """Router meta-reasoning before an answer marker must be stripped.

        Regression: the qwen_direct path used to surface the function-calling
        router's raw deliberation ("...should respond directly without
        triggering the specialist tool") as the user-visible reply.
        """
        fake_ollama.configure(
            router_mode="general",
            chat_reply=(
                "The user is asking a follow-up question, which does not describe a "
                "new symptom. The assistant should respond directly without "
                "triggering the specialist tool.\n\nResponse:\nThe capital of France "
                "is Paris."
            ),
        )

        job_id = (
            await client.post("/v1/chat", json={"message": "what is the capital of France?"})
        ).json()["job_id"]
        result = (await wait_for_job(client, job_id))["result"]

        assert result["path"] == "qwen_direct"
        assert result["response"] == "The capital of France is Paris."
        assert "specialist tool" not in result["response"]
