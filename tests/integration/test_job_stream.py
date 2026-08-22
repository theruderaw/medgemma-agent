"""Job-events SSE: the single streaming channel for every chat turn.

Pipeline events replay from the Redis buffer, token events stream the
specialist note and the final reply as they are generated, and a terminal
``result`` (or ``error``) event closes the stream.
"""

import json

import pytest

from .conftest import drain_sse

pytestmark = pytest.mark.asyncio


class TestJobEventStream:
    async def test_pipeline_events_replay_then_result_terminates(self, client, fake_ollama):
        job_id = (await client.post("/v1/chat", json={"message": "my arm hurts"})).json()["job_id"]

        events = await drain_sse(client, f"/v1/jobs/{job_id}/events")
        names = [name for name, _ in events]

        assert names[-1] == "result"
        assert "pipeline" in names
        payloads = [json.loads(data) for name, data in events if name == "pipeline"]
        event_types = {p["event_type"] for p in payloads}
        assert {"routing_decision", "specialist_output", "turn_completed"} <= event_types

        result = json.loads(events[-1][1])
        assert result["response"]
        assert result["path"] == "medical_specialist"

    async def test_unknown_job_stream_404s(self, client, fake_ollama):
        response = await client.get("/v1/jobs/never-existed/events")
        assert response.status_code == 404

    async def test_specialist_and_reply_tokens_stream(self, client, fake_ollama):
        """Phase-3 contract: both model stages stream deltas through events."""
        job_id = (await client.post("/v1/chat", json={"message": "my arm hurts"})).json()["job_id"]

        events = await drain_sse(client, f"/v1/jobs/{job_id}/events")
        names = [name for name, _ in events]

        assert "specialist_token" in names, "MedGemma JSON must stream live"
        assert "token" in names, "final reply must stream live"

        specialist_text = "".join(
            json.loads(data)["content"] for name, data in events if name == "specialist_token"
        )
        reply_text = "".join(
            json.loads(data)["content"] for name, data in events if name == "token"
        )
        assert "summary" in specialist_text  # raw structured JSON streamed
        assert "monitor your symptoms" in reply_text
