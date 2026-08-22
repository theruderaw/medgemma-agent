"""Triage is off by default and opt-in per request via ?triage=true.

The triage model is text-only MedGemma: image bytes are held back from
triage entirely and only reach the specialist during analysis.
"""

import pytest

from app.core.config import settings

from .conftest import wait_for_job

pytestmark = pytest.mark.asyncio


class TestTriageOptIn:
    async def test_default_turn_skips_triage_entirely(self, client, fake_ollama):
        job_id = (await client.post("/v1/chat", json={"message": "my arm hurts"})).json()["job_id"]
        payload = await wait_for_job(client, job_id)
        result = payload["result"]

        assert fake_ollama.calls("triage") == []
        assert result["urgency"] is None
        assert "triage_result" not in [e["event_type"] for e in result["events"]]

    async def test_query_param_enables_model_triage(self, client, fake_ollama):
        response = await client.post(
            "/v1/chat", params={"triage": "true"}, json={"message": "my arm hurts"}
        )
        job_id = response.json()["job_id"]
        payload = await wait_for_job(client, job_id)
        result = payload["result"]

        assert len(fake_ollama.calls("triage")) == 1
        assert result["urgency"] == "routine"
        event = next(e for e in result["events"] if e["event_type"] == "triage_result")
        assert event["payload"]["urgency"] == "routine"
        assert event["payload"]["model"] == settings.triage_model_name

    async def test_triage_is_text_only_images_go_to_analysis(self, client, fake_ollama, tiny_png):
        response = await client.post(
            "/v1/chat",
            params={"triage": "true"},
            json={
                "message": "look at this bump",
                "image_b64": tiny_png,
                "image_mime": "image/png",
            },
        )
        assert response.status_code == 202
        job_id = response.json()["job_id"]
        await wait_for_job(client, job_id)

        # The triage request body is text-only — no images key anywhere.
        triage_calls = fake_ollama.calls("triage")
        assert len(triage_calls) == 1
        assert "images" not in json_dumps(triage_calls[0])

        # The sanitized image reaches the specialist instead.
        specialist_calls = fake_ollama.calls("specialist")
        assert len(specialist_calls) == 1
        attached = [m for m in specialist_calls[0]["messages"] if m.get("images")]
        assert attached


def json_dumps(body: dict) -> str:
    import json

    return json.dumps(body)
