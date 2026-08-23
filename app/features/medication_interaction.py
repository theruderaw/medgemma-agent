"""Medication-interaction check — dataset-backed, LLM-phrased only.

Unlike the other features, the interaction claim itself NEVER originates
from a model: ``parse()`` extracts exactly two medication names from the
model's structured output, and ``context_for()`` looks the pair up in the
curated dataset (``app/features/data/drug_interactions.json``). The model
only ever phrases/explains what the dataset states. An unknown pair yields
an explicit no-data message — never silence, which would read as "no
interaction exists" (a false negative with real safety consequences).
"""

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .base import SafetyProfile, ToolSchema

MEDICATION_QUERY_FORMAT = {
    "type": "object",
    "properties": {
        "drug_a": {"type": "string"},
        "drug_b": {"type": "string"},
    },
    "required": ["drug_a", "drug_b"],
}

_NO_DATA_CONTEXT = (
    "The user asked about a possible interaction between two medications. "
    "The curated interaction dataset contains NO entry for this combination. "
    "Say plainly that this combination is not in our checked reference data, "
    "so nothing can be concluded either way. Explicitly advise consulting a "
    "pharmacist or clinician before combining the medications. NEVER state "
    "or imply that no interaction exists."
)


# Placeholder values a model may emit instead of a real drug name. Any of
# these in either field means the extraction failed — reject loudly rather
# than look up a nonsense pair (which would read as "no data", not "no hit").
_PLACEHOLDERS = frozenset(
    {"none", "unknown", "n/a", "na", "nil", "null", "not_specified", "no_medication"}
)


@dataclass(frozen=True)
class MedicationPair:
    drug_a: str
    drug_b: str

    def to_dict(self) -> dict:
        return {"drug_a": self.drug_a, "drug_b": self.drug_b}


def _extract_json_object(raw: str) -> dict:
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match is None:
        raise ValueError("No JSON object found in medication query output")
    return json.loads(match.group(0))


@lru_cache(maxsize=1)
def _load_interactions() -> dict:
    path = Path(__file__).parent / "data" / "drug_interactions.json"
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)["interactions"]


class MedicationInteractionFeature:
    name = "check_medication_interaction"
    tool_schema = ToolSchema(
        name="check_medication_interaction",
        description=(
            "Call whenever the patient mentions a medication alongside another "
            "one they take or took — even if only one drug is named in the "
            "latest message and the other comes from earlier in the "
            "conversation, or if they report taking/adding something new. "
            "This runs a curated interaction lookup instead of a general "
            "assessment."
        ),
        parameters={
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "The medication names mentioned and the user's question.",
                }
            },
            "required": ["reason"],
        },
    )
    system_prompt = (
        "You extract medication names. From the patient text, identify the "
        "two medications whose combination the patient is asking about. "
        "Respond with JSON only:\n"
        '{"drug_a": "<first medication>", "drug_b": "<second medication>"}\n'
        "Rules:\n"
        "- Use lowercase generic names when known.\n"
        "- Every query concerns exactly two real medications. If only one is "
        "named in the patient text, take the other from the surrounding "
        "conversation summary (e.g. a drug the patient said they already "
        "take).\n"
        "- NEVER write \"none\", \"unknown\", \"n/a\" or any other "
        "placeholder: both fields must be real medication names.\n"
        "- Extract only medications actually present in the text or "
        "conversation; never invent or substitute medications.\n"
        "- Do not assess, explain, or judge any interaction yourself."
    )
    safety_profile = SafetyProfile(
        requires_professional_review=True,
        disclaimer_level="high",
    )
    model_setting = "specialist_model_name"
    format_schema = MEDICATION_QUERY_FORMAT

    def parse(self, raw_model_output: str) -> MedicationPair:
        """Parse the model's structured extraction into a normalized pair.

        Missing/empty drug names raise ValueError rather than degrading into
        a guess against the dataset.
        """
        data = _extract_json_object(raw_model_output)
        drug_a = str(data.get("drug_a") or "").strip().lower()
        drug_b = str(data.get("drug_b") or "").strip().lower()
        if not drug_a or not drug_b:
            raise ValueError("Medication query output missing a drug name")
        if drug_a in _PLACEHOLDERS or drug_b in _PLACEHOLDERS:
            raise ValueError(
                f"Medication query output contains a placeholder name: "
                f"'{drug_a}', '{drug_b}'"
            )
        return MedicationPair(drug_a=drug_a, drug_b=drug_b)

    def context_for(self, result: MedicationPair, **kwargs) -> str | None:
        interactions = _load_interactions()
        key = "+".join(sorted((result.drug_a, result.drug_b)))
        entry = interactions.get(key)
        if entry is None:
            return _NO_DATA_CONTEXT
        return (
            f"The user asked about taking {result.drug_a} and {result.drug_b} "
            "together. A curated drug-reference dataset states the following "
            "(this is authoritative; you may phrase and explain it but must "
            f"not alter, weaken, or extend its claims):\n"
            f"Severity: {entry['severity']}.\n"
            f"Effect: {entry['effect']}\n"
            f"Guidance: {entry['guidance']}"
        )


medication_interaction_feature = MedicationInteractionFeature()
