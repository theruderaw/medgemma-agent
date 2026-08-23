"""Router-selectable add-on features (Step 3): symptom triage + medication interaction.

The always-on ``triage=True`` flag path has its own suite
(``test_triage_opt_in.py``); here the router itself selects the feature tool.

The medication-interaction feature additionally exercises the dispatcher's
optional capability hooks: deterministic extraction/reply (no model calls for
the extraction/synthesis stages), the conservative keyword routing override,
and the fault-isolation boundary (a failing feature degrades into an explicit
unavailable reply instead of failing the turn).
"""

import json

from app.core.config import settings
from app.features.medication_interaction import (
    MedicationInteractionFeature,
    MedicationPair,
)

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
    async def test_known_pair_takes_deterministic_fast_path(self, client, fake_ollama):
        """Two known drugs in the message: the regex extractor answers without
        any LLM extraction call, and the dataset template phrases the reply."""
        result = await _completed_result(
            client,
            fake_ollama,
            message="can I take warfarin and ibuprofen together?",
            router_tool_call_name="check_medication_interaction",
        )

        output = _event(result, "specialist_output")
        assert output["payload"]["mode"] == "deterministic"
        assert output["payload"]["result"] == {
            "drug_a": "ibuprofen",
            "drug_b": "warfarin",
        }
        # The streamed LLM extraction stage never ran.
        assert fake_ollama.calls("medication") == []
        completed = _event(result, "turn_completed")
        assert completed["payload"]["path"] == "medical_specialist"
        assert "Interaction check:" in result["response"]
        assert "major" in result["response"]
        assert "bleeding" in result["response"].lower()

    async def test_brand_aliases_resolve_deterministically(self, client, fake_ollama):
        """Brand names map onto canonical generics before the dataset lookup."""
        result = await _completed_result(
            client,
            fake_ollama,
            message="is it okay to take Advil while on Coumadin?",
            router_tool_call_name="check_medication_interaction",
        )

        output = _event(result, "specialist_output")
        assert output["payload"]["mode"] == "deterministic"
        assert output["payload"]["result"] == {
            "drug_a": "ibuprofen",
            "drug_b": "warfarin",
        }
        assert fake_ollama.calls("medication") == []

    async def test_llm_fallback_when_drugs_are_unknown(self, client, fake_ollama):
        """No known alias anywhere: deterministic extraction returns None and
        the streamed LLM stage runs exactly as before."""
        result = await _completed_result(
            client,
            fake_ollama,
            message="is xanax okay with echinacea?",
            router_tool_call_name="check_medication_interaction",
            medication_json=json.dumps({"drug_a": "xanax", "drug_b": "echinacea"}),
        )
        output = _event(result, "specialist_output")
        assert output["payload"]["mode"] == "llm"
        assert output["payload"]["result"] == {"drug_a": "xanax", "drug_b": "echinacea"}
        assert len(fake_ollama.calls("medication")) == 1
        assert _event(result, "turn_completed")["payload"]["path"] == "medical_specialist"
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

    async def test_feature_failure_degrades_to_unavailable_reply(self, client, fake_ollama):
        """Fault-isolation boundary: a feature that raises mid-turn must never
        fail the turn — an explicit unavailable reply completes it, and the
        failure is audited as a feature_failed event."""
        result = await _completed_result(
            client,
            fake_ollama,
            message="is xanax okay with echinacea?",
            router_tool_call_name="check_medication_interaction",
            # Placeholder name -> parse() raises ValueError inside the worker.
            medication_json=json.dumps({"drug_a": "none", "drug_b": ""}),
        )

        failed = _event(result, "feature_failed")
        assert failed["payload"]["feature"] == "check_medication_interaction"
        assert failed["payload"]["error"].startswith("ValueError")

        assert not [e for e in result["events"] if e["event_type"] == "specialist_output"]
        completed = _event(result, "turn_completed")
        assert completed["payload"]["path"] == "feature_unavailable"
        assert "temporarily unavailable" in result["response"]
        # The professional-review note still applies on top of the fallback.
        assert "qualified healthcare professional" in result["response"]


class TestKeywordRoutingOverride:
    async def test_trigger_upgrades_general_router_decision(self, client, fake_ollama):
        """Router answered GENERAL, but two known drugs are mentioned: the
        conservative keyword trigger forces dispatch to the feature."""
        result = await _completed_result(
            client,
            fake_ollama,
            message="quick question — can I take advil with coumadin?",
            router_mode="direct",
            chat_reply="That is a general knowledge question.",
        )

        routing = _event(result, "routing_decision")
        assert routing["payload"]["category"] == "symptom_related"
        assert routing["payload"]["keyword_override"] is True
        assert fake_ollama.calls("medication") == []
        assert _event(result, "turn_completed")["payload"]["path"] == "medical_specialist"
        assert "Interaction check:" in result["response"]

    async def test_no_trigger_without_known_drugs(self, client, fake_ollama):
        """Ordinary GENERAL turns are never hijacked by stale history."""
        result = await _completed_result(
            client,
            fake_ollama,
            message="what is the capital of France?",
            router_mode="direct",
        )

        routing = _event(result, "routing_decision")
        assert routing["payload"]["keyword_override"] is False
        assert result["path"] == "qwen_direct"


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


class TestDeterministicHooks:
    """Unit-level coverage of the optional capability hooks."""

    async def test_extract_from_message_and_history(self):
        feature = MedicationInteractionFeature()
        pair = feature.deterministic_extract(
            "should I add aspirin?",
            [
                {"role": "user", "content": "I take warfarin daily"},
                {"role": "assistant", "content": "noted"},
                {"role": "user", "content": "should I add aspirin?"},
            ],
        )
        assert pair == MedicationPair(drug_a="aspirin", drug_b="warfarin")

    async def test_extract_returns_none_below_two_known_drugs(self):
        feature = MedicationInteractionFeature()
        assert feature.deterministic_extract("my head hurts", []) is None
        assert feature.deterministic_extract("", []) is None

    async def test_route_trigger_requires_current_message_contribution(self):
        feature = MedicationInteractionFeature()
        history = [{"role": "user", "content": "warfarin and aspirin discussion"}]
        # Two known drugs in history alone must NOT fire...
        assert not feature.route_trigger("what is the flu?", history)
        # ...but one current mention plus history does.
        assert feature.route_trigger("can I take advil too?", history)

    async def test_reply_known_pair_templates_the_dataset(self):
        feature = MedicationInteractionFeature()
        pair = MedicationPair(drug_a="ibuprofen", drug_b="warfarin")
        reply = feature.deterministic_reply(pair)
        assert "major severity" in reply
        assert "bleeding" in reply.lower()
        assert "clinician" in reply.lower()

        aspair = MedicationPair(drug_a="aspirin", drug_b="warfarin")
        assert "INR" in feature.deterministic_reply(aspair)

    async def test_reply_unknown_pair_never_implies_absence(self):
        feature = MedicationInteractionFeature()
        reply = feature.deterministic_reply(MedicationPair(drug_a="xanax", drug_b="echinacea"))
        assert "not in our checked reference data" in reply
        assert "pharmacist" in reply.lower()
