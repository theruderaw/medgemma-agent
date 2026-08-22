"""Image turns: sanitize → audit → force specialist routing → reach analysis.

An attached image is clinical evidence: the router can never drop it, and
the image bytes only ever go to the specialist (never triage).
"""

import base64

import pytest

from .conftest import wait_for_job

pytestmark = pytest.mark.asyncio


class TestImageTurns:
    async def test_image_is_audited_and_reaches_specialist(self, client, fake_ollama, tiny_png):
        response = await client.post(
            "/v1/chat",
            json={
                "message": "look at this bump",
                "image_b64": tiny_png,
                "image_mime": "image/png",
            },
        )
        job_id = response.json()["job_id"]
        result = (await wait_for_job(client, job_id))["result"]

        received = next(e for e in result["events"] if e["event_type"] == "image_received")
        assert len(received["payload"]["sha256"]) == 64
        assert received["payload"]["mime"] == "image/jpeg"  # sanitized + re-encoded

        # The specialist analyzed exactly one sanitized image.
        specialist_calls = fake_ollama.calls("specialist")
        assert len(specialist_calls) == 1
        attached = [m for m in specialist_calls[0]["messages"] if m.get("images")]
        assert len(attached) == 1
        base64.b64decode(attached[0]["images"][0])  # valid base64

    async def test_router_cannot_drop_an_attached_image(self, client, fake_ollama, tiny_png):
        fake_ollama.configure(router_mode="general")

        response = await client.post(
            "/v1/chat",
            json={
                "message": "look at this bump",
                "image_b64": tiny_png,
                "image_mime": "image/png",
            },
        )
        job_id = response.json()["job_id"]
        result = (await wait_for_job(client, job_id))["result"]

        routing = next(e for e in result["events"] if e["event_type"] == "routing_decision")
        assert routing["payload"]["image_override"] is True
        assert result["path"] == "medical_specialist"
        assert fake_ollama.calls("specialist"), "image must be analyzed even when router declines"

    async def test_invalid_image_rejected_422(self, client):
        response = await client.post(
            "/v1/chat",
            json={"message": "x", "image_b64": "not-valid-image-data", "image_mime": "image/png"},
        )
        assert response.status_code == 422

    async def test_half_pair_rejected_422(self, client):
        response = await client.post("/v1/chat", json={"message": "x", "image_b64": "aaaa"})
        assert response.status_code == 422

    async def test_image_without_triage_never_hits_triage_model(self, client, fake_ollama, tiny_png):
        response = await client.post(
            "/v1/chat",
            json={
                "message": "look at this",
                "image_b64": tiny_png,
                "image_mime": "image/png",
            },
        )
        job_id = response.json()["job_id"]
        await wait_for_job(client, job_id)
        assert fake_ollama.calls("triage") == []
