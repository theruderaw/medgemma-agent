"""Session persistence: postgres-backed history, reset, expiry semantics."""

import pytest

from .conftest import db_fetch, wait_for_job

pytestmark = pytest.mark.asyncio


class TestSessionPersistence:
    async def test_history_roundtrips_across_turns(self, client, fake_ollama):
        first = await client.post("/v1/chat", json={"message": "first message"})
        session_id = first.json()["session_id"]

        second = await client.post(
            "/v1/chat", json={"message": "second message", "session_id": session_id}
        )
        assert second.status_code == 202
        await wait_for_job(client, second.json()["job_id"])

        rows = await db_fetch(
            "SELECT role, content FROM messages WHERE session_id = $1 ORDER BY seq",
            session_id,
        )
        contents = [row["content"] for row in rows]
        assert "first message" in contents
        assert "second message" in contents

        # The second turn's router context included the prior history.
        route_calls = fake_ollama.calls("route")
        assert len(route_calls) == 2
        routed_messages = route_calls[1]["messages"]
        assert any(
            m["role"] == "user" and m["content"] == "first message" for m in routed_messages
        )

    async def test_reset_deletes_session_and_future_turns_410(self, client):
        session_id = (await client.post("/v1/chat", json={"message": "hi"})).json()["session_id"]

        deleted = await client.delete(f"/v1/sessions/{session_id}")
        assert deleted.status_code == 204

        again = await client.delete(f"/v1/sessions/{session_id}")
        assert again.status_code == 404

        follow_up = await client.post(
            "/v1/chat", json={"message": "back", "session_id": session_id}
        )
        assert follow_up.status_code == 410

    async def test_full_history_retained_in_postgres(self, client):
        """Postgres never trims: every exchange stays reconstructable."""
        session_id = None
        job_ids = []
        for i in range(6):
            payload = {"message": f"turn {i}"}
            if session_id:
                payload["session_id"] = session_id
            response = await client.post("/v1/chat", json=payload)
            session_id = response.json()["session_id"]
            job_ids.append(response.json()["job_id"])

        for job_id in job_ids:
            await wait_for_job(client, job_id)

        rows = await db_fetch(
            "SELECT role, content FROM messages WHERE session_id = $1 ORDER BY seq",
            session_id,
        )
        user_turns = [r["content"] for r in rows if r["role"] == "user"]
        assert user_turns == [f"turn {i}" for i in range(6)]
