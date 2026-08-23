"""Safety behavior: the regex emergency floor and always-on output guardrails."""

import json

import pytest

from app.safety.invariants import PROFESSIONAL_REVIEW_NOTE
from app.safety.output import DIAGNOSTIC_CAUTION

from .conftest import wait_for_job

pytestmark = pytest.mark.asyncio


def _guard_verdict(**flags) -> str:
    base = {
        "diagnostic_claim": False,
        "missing_disclaimer": False,
        "emergency_bypass": False,
        "triage_contradiction": False,
        "unsafe_wording": False,
        "reasoning": "test verdict",
    }
    base.update(flags)
    return json.dumps(base)


LONG_CLEAN_REPLY = (
    "Elbow pain after activity is common and often settles with rest. Apply ice "
    "for fifteen minutes a few times a day, avoid movements that provoke the pain, "
    "and use an over-the-counter pain reliever if that suits you. If the pain lasts "
    "beyond two weeks, worsens, or comes with numbness or swelling, please see a "
    "clinician for a hands-on assessment."
)


class TestEmergencyFloor:
    async def test_red_flag_short_circuits_synchronously(self, client, fake_ollama):
        response = await client.post("/v1/chat", json={"message": "I have chest pain"})
        assert response.status_code == 200
        body = response.json()

        assert body["urgency"] == "emergency"
        assert "emergency" in body["response"].lower()
        assert any(e["event_type"] == "safety_override" for e in body["events"])

        # No model ran: the floor is pure application code.
        assert fake_ollama.calls("route") == []
        assert fake_ollama.calls("specialist") == []
        assert fake_ollama.calls("triage") == []

    async def test_floor_precedes_triage_opt_in_and_images(self, client, fake_ollama, tiny_png):
        response = await client.post(
            "/v1/chat",
            params={"triage": "true"},
            json={
                "message": "severe bleeding since the accident",
                "image_b64": tiny_png,
                "image_mime": "image/png",
            },
        )
        assert response.status_code == 200
        assert response.json()["urgency"] == "emergency"
        assert fake_ollama.calls("specialist") == []


class TestSafetyInvariants:
    async def test_emergency_triage_cannot_be_downgraded(self, client, fake_ollama):
        """Structured triage says EMERGENCY but the drafted reply is not the
        hardcoded emergency template → the deterministic invariant replaces
        it and records a safety_invariant event."""
        fake_ollama.configure(triage_json=json.dumps({"urgency": "emergency"}))

        response = await client.post(
            "/v1/chat", params={"triage": "true"}, json={"message": "my elbow hurts"}
        )
        assert response.status_code == 202
        result = (await wait_for_job(client, response.json()["job_id"]))["result"]

        invariant_events = [
            e for e in result["events"] if e["event_type"] == "safety_invariant"
        ]
        assert invariant_events, "emergency downgrade must be flagged"
        assert "emergency_bypass" in invariant_events[0]["payload"]["violations"]
        assert "replace_emergency_response" in invariant_events[0]["payload"]["actions"]
        assert "local emergency number" in result["response"]


class TestSafetyProfiles:
    async def _completed(
        self,
        client,
        fake_ollama,
        *,
        message: str,
        triage: bool = False,
        **config,
    ) -> dict:
        fake_ollama.configure(**config)
        response = await client.post(
            "/v1/chat",
            params={"triage": "true"} if triage else None,
            json={"message": message},
        )
        assert response.status_code == 202
        return (await wait_for_job(client, response.json()["job_id"]))["result"]

    async def test_high_disclaimer_feature_gets_review_note(self, client, fake_ollama):
        """Medication interaction (disclaimer_level=high) always carries the
        professional-review note, recorded via the violations/actions pattern."""
        result = await self._completed(
            client,
            fake_ollama,
            message="can I take warfarin and ibuprofen together?",
            router_tool_call_name="check_medication_interaction",
        )

        assert PROFESSIONAL_REVIEW_NOTE in result["response"]
        invariant_events = [
            e for e in result["events"] if e["event_type"] == "safety_invariant"
        ]
        assert invariant_events
        assert "profile_professional_review" in invariant_events[0]["payload"]["violations"]
        assert (
            "append_professional_review_note" in invariant_events[0]["payload"]["actions"]
        )

    async def test_standard_disclaimer_feature_gets_no_extra_note(self, client, fake_ollama):
        """Symptom triage (standard disclaimer) must NOT carry the note."""
        result = await self._completed(
            client,
            fake_ollama,
            message="my elbow hurts a little",
            router_tool_call_name="run_symptom_triage",
            triage_json=json.dumps({"urgency": "routine"}),
        )

        assert PROFESSIONAL_REVIEW_NOTE not in result["response"]
        assert not [e for e in result["events"] if e["event_type"] == "safety_invariant"]

    async def test_emergency_floor_overrides_any_profile(self, client, fake_ollama):
        """The red-flag floor runs before routing: even with the router set to
        select the strictest-profile feature, nothing else may run or speak."""
        response = await client.post(
            "/v1/chat",
            json={"message": "I have chest pain"},
        )
        assert response.status_code == 200
        body = response.json()

        assert body["urgency"] == "emergency"
        assert any(e["event_type"] == "safety_override" for e in body["events"])
        assert PROFESSIONAL_REVIEW_NOTE not in body["response"]
        assert fake_ollama.calls("route") == []
        assert fake_ollama.calls("medication") == []

    async def test_emergency_triage_replacement_ignores_profile(self, client, fake_ollama):
        """Structured EMERGENCY triage + a high-profile feature selected: the
        draft is replaced by the hardcoded template and the profile note is
        never appended to it — the floor's text is untouchable."""
        result = await self._completed(
            client,
            fake_ollama,
            message="my stomach hurts",
            triage=True,
            router_tool_call_name="check_medication_interaction",
            triage_json=json.dumps({"urgency": "emergency"}),
        )

        assert "local emergency number" in result["response"]
        assert PROFESSIONAL_REVIEW_NOTE not in result["response"]
        invariant_events = [
            e for e in result["events"] if e["event_type"] == "safety_invariant"
        ]
        assert "emergency_bypass" in invariant_events[0]["payload"]["violations"]


class TestOutputGuardrails:
    async def _completed_result(self, client, job_id) -> dict:
        return (await wait_for_job(client, job_id))["result"]

    async def test_guard_model_consulted_on_long_triaged_turns(self, client, fake_ollama):
        """Urgency set + reply ≥ guard_min_chars → the guard model must run."""
        fake_ollama.configure(chat_reply=LONG_CLEAN_REPLY)

        response = await client.post(
            "/v1/chat", params={"triage": "true"}, json={"message": "my elbow hurts"}
        )
        result = await self._completed_result(client, response.json()["job_id"])

        assert len(fake_ollama.calls("guard")) == 1
        assert "output_guardrail" not in [e["event_type"] for e in result["events"]]
        assert result["response"].startswith("Elbow pain")

    async def test_diagnostic_claim_gets_caution_appended(self, client, fake_ollama):
        long_reply = (
            "You definitely have tennis elbow. This is certainly a case of lateral "
            "epicondylitis caused by your grip technique, and the pain will keep "
            "getting worse every single day until it is treated by a professional."
        )
        fake_ollama.configure(
            chat_reply=long_reply,
            guard_json=_guard_verdict(diagnostic_claim=True),
        )

        response = await client.post(
            "/v1/chat", params={"triage": "true"}, json={"message": "my elbow hurts"}
        )
        result = await self._completed_result(client, response.json()["job_id"])

        guard_events = [e for e in result["events"] if e["event_type"] == "output_guardrail"]
        assert guard_events, "diagnostic claim must be flagged"
        assert "diagnostic_claim" in guard_events[0]["payload"]["violations"]
        assert DIAGNOSTIC_CAUTION in result["response"]

    async def test_clean_short_reply_skips_guard_model(self, client, fake_ollama):
        response = await client.post("/v1/chat", json={"message": "my arm hurts"})
        result = await self._completed_result(client, response.json()["job_id"])

        # No triage urgency + short reply → deterministic gate skips the LLM call.
        assert fake_ollama.calls("guard") == []
        assert "output_guardrail" not in [e["event_type"] for e in result["events"]]
