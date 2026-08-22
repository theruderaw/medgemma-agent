"""Router-selectable add-on features (Step 3): symptom triage + medication interaction.

The always-on ``triage=True`` flag path has its own suite
(``test_triage_opt_in.py``); here the router itself selects the feature tool.
"""

import json

from app.core.config import settings
from app.features.medication_interaction import MedicationInteractionFeature

from .conftest import wait_for_job


async def _completed_result(client, fake_ollama, *, message: str, **config) -> dict:
    fake_ollama.configure(**config)
    response = await client.post("/v1/chat", json={"message": message})
    assert response.status_code == 202
    return (await wait_for_job(client, response.json()["job_id"]))["result"]


def _event(result: dict, event_type: str) -> dict:
    matches = [e for e in result["events"] if e["event_type"] == event_type]
    assert matches, f"expected a {event_type} event in {result['events']}"
    return matches[0]


class TestSymptomTriageFeature:
    async def test_router_selects_triage_tool(self, client, fake_ollama):
        result = await _completed_result(
            client,
            fake_ollama,
            message="my elbow hurts a little",
            router_tool_call_name="run_symptom_triage",
            triage_json=json.dumps({"urgency": "routine"}),
        )

        routing = _event(result, "routing_decision")
        assert routing["payload"]["category"] == "symptom_related"

        output = _event(result, "specialist_output")
        assert output["payload"]["result"]["urgency"] == "routine"
        # The streamed stage ran on the triage model via model_setting.
        assert output["payload"]["model"] == settings.triage_model_name

        completed = _event(result, "turn_completed")
        assert completed["payload"]["path"] == "medical_specialist"
        assert result["response"]

    async def test_router_not_selecting_any_tool_answers_directly(self, client, fake_ollama):
        result = await _completed_result(
            client,
            fake_ollama,
            message="hello there",
            router_mode="direct",
        )

        routing = _event(result, "routing_decision")
        assert routing["payload"]["category"] == "general"
        assert not [e for e in result["events"] if e["event_type"] == "specialist_output"]
        assert fake_ollama.calls("triage") == []
        assert fake_ollama.calls("medication") == []
        assert result["path"] == "qwen_direct"


class TestMedicationInteractionFeature:
    async def test_known_pair_completes_with_extracted_drugs(self, client, fake_ollama):
        result = await _completed_result(
            client,
            fake_ollama,
            message="can I take warfarin and ibuprofen together?",
            router_tool_call_name="check_medication_interaction",
            medication_json=json.dumps({"drug_a": "Warfarin", "drug_b": "ibuprofen"}),
        )

        output = _event(result, "specialist_output")
        assert output["payload"]["result"] == {"drug_a": "warfarin", "drug_b": "ibuprofen"}
        assert len(fake_ollama.calls("medication")) == 1
        completed = _event(result, "turn_completed")
        assert completed["payload"]["path"] == "medical_specialist"
        assert result["response"]

    async def test_unknown_pair_still_completes_safely(self, client, fake_ollama):
        """The highest-consequence branch: pair absent from the dataset must
        complete (explicit no-data context) instead of failing the turn."""
        result = await _completed_result(
            client,
            fake_ollama,
            message="is xanax okay with echinacea?",
            router_tool_call_name="check_medication_interaction",
            medication_json=json.dumps({"drug_a": "xanax", "drug_b": "echinacea"}),
        )
        assert _event(result, "turn_completed")["payload"]["path"] == "medical_specialist"
        assert result["response"]


def test_context_for_known_pair_states_dataset_claims():
    feature = MedicationInteractionFeature()
    context = feature.context_for(feature.parse('{"drug_a": "Ibuprofen", "drug_b": "warfarin"}'))
    assert "major" in context
    assert "bleeding" in context.lower()


def test_context_for_unknown_pair_never_implies_absence():
    feature = MedicationInteractionFeature()
    context = feature.context_for(feature.parse('{"drug_a": "xanax", "drug_b": "echinacea"}'))
    assert "NO entry" in context
    assert "pharmacist" in context.lower()
