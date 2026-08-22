"""GET /v1/audit — read-only view of the append-only audit trail.

The `id` param scopes the listing to one session; newest events come first.
"""

import pytest

from .conftest import db_fetchone, wait_for_job

pytestmark = pytest.mark.asyncio


class TestAuditEndpoint:
    async def test_id_scopes_to_session_and_orders_newest_first(self, client):
        body = (await client.post("/v1/chat", json={"message": "my arm hurts"})).json()
        session_id = body["session_id"]
        await wait_for_job(client, body["job_id"])

        response = await client.get("/v1/audit", params={"id": session_id})
        assert response.status_code == 200
        events = response.json()["events"]

        assert events, "a completed turn must leave an audit trail"
        assert all(e["session_id"] == session_id for e in events)
        ids = [e["id"] for e in events]
        assert ids == sorted(ids, reverse=True), "newest first"

        types = {e["event_type"] for e in events}
        assert "job_enqueued" in types
        assert "turn_completed" in types

    async def test_without_id_returns_latest_across_sessions(self, client):
        first = (await client.post("/v1/chat", json={"message": "hi"})).json()
        second = (await client.post("/v1/chat", json={"message": "hello"})).json()
        await wait_for_job(client, first["job_id"])
        await wait_for_job(client, second["job_id"])

        response = await client.get("/v1/audit", params={"limit": 100})
        assert response.status_code == 200
        events = response.json()["events"]

        session_ids = {e["session_id"] for e in events}
        assert {first["session_id"], second["session_id"]} <= session_ids

    async def test_limit_caps_page_size(self, client):
        body = (await client.post("/v1/chat", json={"message": "hi"})).json()
        await wait_for_job(client, body["job_id"])

        response = await client.get("/v1/audit", params={"id": body["session_id"], "limit": 2})
        assert len(response.json()["events"]) == 2

        bad = await client.get("/v1/audit", params={"limit": 0})
        assert bad.status_code == 422

    async def test_unknown_session_yields_empty_list(self, client):
        response = await client.get("/v1/audit", params={"id": "never-existed"})
        assert response.status_code == 200
        assert response.json()["events"] == []

    async def test_emergency_floor_is_audited(self, client):
        body = (await client.post("/v1/chat", json={"message": "I have chest pain"}))
        assert body.status_code == 200
        session_id = body.json()["session_id"]

        response = await client.get("/v1/audit", params={"id": session_id})
        types = [e["event_type"] for e in response.json()["events"]]
        assert "safety_override" in types

    async def test_rows_backed_by_postgres_table(self, client):
        body = (await client.post("/v1/chat", json={"message": "hi"})).json()
        await wait_for_job(client, body["job_id"])

        row = await db_fetchone(
            "SELECT module, event_type FROM audit_events WHERE session_id = $1 "
            "ORDER BY id DESC LIMIT 1",
            body["session_id"],
        )
        assert row is not None
