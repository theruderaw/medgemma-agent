"""Standalone /v1/triage endpoint: rules floor, text-only model classification."""

import json

import pytest

from app.core.config import settings

pytestmark = pytest.mark.asyncio


class TestTriageEndpoint:
    async def test_red_flag_rules_short_circuit_without_model(self, client, fake_ollama):
        response = await client.post("/v1/triage", json={"message": "I cannot breathe"})
        assert response.status_code == 200
        body = response.json()

        assert body["urgency"] == "emergency"
        assert body["source"] == "rules"
        assert body["model"] == "hardcoded_rules"
        assert body["red_flags"]
        assert fake_ollama.calls("triage") == []

    async def test_model_classification_for_plain_text(self, client, fake_ollama):
        response = await client.post(
            "/v1/triage", json={"message": "mild rash on my forearm for two days"}
        )
        assert response.status_code == 200
        body = response.json()

        assert body["urgency"] == "routine"
        assert body["source"] == "text"
        assert body["model"] == settings.triage_model_name
        assert len(fake_ollama.calls("triage")) == 1

    async def test_image_stored_and_audited_but_never_classified(self, client, fake_ollama, tiny_png):
        response = await client.post(
            "/v1/triage",
            json={
                "message": "photo of a rash",
                "image_b64": tiny_png,
                "image_mime": "image/png",
            },
        )
        assert response.status_code == 200
        body = response.json()

        assert body["source"] == "text", "images never influence urgency"
        assert body["image"]["sha256"]
        # The triage model call carries text only — no images key exists in
        # the request payload at all.
        triage_calls = fake_ollama.calls("triage")
        assert len(triage_calls) == 1
        assert "images" not in json.dumps(triage_calls[0])
