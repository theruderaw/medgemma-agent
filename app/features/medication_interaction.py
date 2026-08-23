"""Medication-interaction check — dataset-backed, deterministic-first.

Unlike the other features, the interaction claim itself NEVER originates
from a model: the pair is looked up in the curated dataset
(``app/features/data/drug_interactions.json``) and any model output is only
ever used to phrase/explain what the dataset states. An unknown pair yields
an explicit no-data message — never silence, which would read as "no
interaction exists" (a false negative with real safety consequences).

This feature additionally implements the optional dispatcher capability
hooks (see ``app/features/base.py``):

- ``deterministic_extract`` — regex-over-known-aliases extraction from the
  message + recent history. Returns None when fewer than two known drugs are
  present so the streamed LLM extraction stage remains the fallback.
- ``deterministic_reply``   — severity-keyed template phrasing straight from
  the dataset entry (the synthesis LLM is skipped; safety layers still run).
- ``route_trigger``         — conservative keyword claim used only when the
  router decided GENERAL: requires at least one known drug in the *current*
  message and two distinct known drugs across message + recent history.
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

_NO_DATA_REPLY = (
    "{drug_a} + {drug_b} is not in our checked reference data, so nothing "
    "can be concluded about this combination either way — do not take that "
    "as evidence it is safe. Please consult a pharmacist or clinician "
    "before combining these medications."
)

_REPLY_TEMPLATE = (
    "Interaction check: {drug_a} + {drug_b} — {severity} severity.\n"
    "What can happen: {effect}\n"
    "What to do: {guidance}\n"
    "This is a reference-database lookup, not a personal medical "
    "assessment. Confirm with your doctor or pharmacist before combining "
    "or changing any medications."
)

# How much conversation history the deterministic scanner considers (tail of
# the built message list, user messages only).
_HISTORY_WINDOW = 12


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
def _load_dataset() -> tuple[dict, dict[str, str]]:
    """Load the curated dataset once: (interactions, alias->generic index).

    Aliases whose target is not a drug appearing in some interaction key are
    ignored — an alias must never introduce a drug the dataset cannot answer
    for. Generic names always map to themselves.
    """
    path = Path(__file__).parent / "data" / "drug_interactions.json"
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    interactions: dict = data["interactions"]
    known = {name for key in interactions for name in key.split("+")}
    aliases: dict[str, str] = {}
    for alias, generic in data.get("aliases", {}).items():
        if alias.startswith("_"):
            continue
        if generic in known:
            aliases[alias.lower()] = generic
    for name in known:
        aliases.setdefault(name, name)
    return interactions, aliases


def _load_interactions() -> dict:
    return _load_dataset()[0]


@lru_cache(maxsize=1)
def _drug_pattern() -> re.Pattern:
    """Single case-insensitive word-boundary alternation over every known
    name/alias, longest first so brand multi-words win over substrings."""
    _, aliases = _load_dataset()
    alternatives = "|".join(
        re.escape(name) for name in sorted(aliases, key=len, reverse=True)
    )
    return re.compile(rf"\b(?:{alternatives})\b", re.IGNORECASE)


def _history_texts(history: list[dict] | None) -> list[str]:
    if not history:
        return []
    return [
        str(msg.get("content") or "")
        for msg in history[-_HISTORY_WINDOW:]
        if msg.get("role") == "user"
    ]


def _find_drugs(*texts: str) -> set[str]:
    """Canonical generic names mentioned anywhere in the given texts."""
    _, aliases = _load_dataset()
    found: set[str] = set()
    for text in texts:
        if not text:
            continue
        for match in _drug_pattern().finditer(text):
            found.add(aliases[match.group(0).lower()])
    return found


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
    unavailable_reply = (
        "The medication interaction check is temporarily unavailable, so I "
        "could not look this combination up. Please consult a pharmacist or "
        "clinician before combining or changing any medications."
    )

    def deterministic_extract(self, text: str, history: list[dict]) -> MedicationPair | None:
        """Deterministic pair extraction over known names/aliases.

        Scans the current message plus the recent history tail. Returns None
        when fewer than two distinct known drugs are present anywhere, leaving
        the LLM extraction stage as the fallback for fuzzy cases (misspellings,
        unrecognized brands, pronoun-only follow-ups).
        """
        found = _find_drugs(text, *_history_texts(history))
        if len(found) < 2:
            return None
        drug_a, drug_b = sorted(found)[:2]
        return MedicationPair(drug_a=drug_a, drug_b=drug_b)

    def route_trigger(self, text: str, history: list[dict]) -> bool:
        """Conservative deterministic routing claim.

        Requires at least one known drug in the *current* message (so ordinary
        conversation is never hijacked by stale history) and two distinct
        known drugs across message + recent history tail.
        """
        current = _find_drugs(text)
        if not current:
            return False
        total = current | _find_drugs(*_history_texts(history))
        return len(total) >= 2

    def deterministic_reply(self, result: MedicationPair) -> str:
        """Template phrasing straight from the curated dataset entry."""
        entry = _load_interactions().get(
            "+".join(sorted((result.drug_a, result.drug_b)))
        )
        if entry is None:
            return _NO_DATA_REPLY.format(drug_a=result.drug_a, drug_b=result.drug_b)
        return _REPLY_TEMPLATE.format(
            drug_a=result.drug_a,
            drug_b=result.drug_b,
            severity=entry["severity"],
            effect=entry["effect"],
            guidance=entry["guidance"],
        )

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
