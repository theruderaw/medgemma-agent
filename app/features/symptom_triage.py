"""Symptom-triage feature — the existing MedGemma triage, router-selectable.

Glue-only migration (Step 3.1): the prompt lives in ``app/prompts/triage.py``,
parsing in ``app/triage/parsing.py``, and the always-on ``triage=True``
request flag path in ``run_chat_turn`` is untouched. Registering this feature
only adds its tool schema to the router's option set, so a turn can get a
lightweight urgency read without escalating to the full clinical assessment.
"""

from ..prompts.triage import TRIAGE_FORMAT, TRIAGE_INSTRUCTIONS, triage_context_for
from ..triage import TriageResult, parse_triage_result
from .base import SafetyProfile, ToolSchema


class SymptomTriageFeature:
    name = "run_symptom_triage"
    tool_schema = ToolSchema(
        name="run_symptom_triage",
        description=(
            "Call for a lightweight urgency read on a described symptom "
            "when a full clinical assessment isn't yet warranted — use "
            "before escalating to call_medical_specialist for ambiguous or "
            "early-stage descriptions."
        ),
        parameters={
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "Concise summary of why an urgency read is needed.",
                }
            },
            "required": ["reason"],
        },
    )
    system_prompt = TRIAGE_INSTRUCTIONS
    safety_profile = SafetyProfile(
        requires_professional_review=False,
        disclaimer_level="standard",
    )
    model_setting = "triage_model_name"
    format_schema = TRIAGE_FORMAT

    def parse(self, raw_model_output: str) -> TriageResult:
        return parse_triage_result(raw_model_output)

    def context_for(self, result: TriageResult, **kwargs) -> str | None:
        return triage_context_for(result)


symptom_triage_feature = SymptomTriageFeature()
