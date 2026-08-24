"""Structured prescription transcription — the read_prescription result type.

The model's ONLY job is verbatim transcription into the enforced wire
contract (``app/prompts/formats.py::PRESCRIPTION_FORMAT``): a medications
map keyed by drug name. Uncertainty is never modeled by the network — it is
derived here, deterministically, from what came back: an empty map, a
missing key, or placeholder names mean "could not read", never "none
found". Identity fields (patient, prescriber) are not part of the contract
and are dropped wherever they appear.
"""

import json
import re
from dataclasses import dataclass, field

_MEDICATION_FIELDS = ("strength", "dose", "frequency", "duration", "instructions")

# Human-readable labels for clarification prompts (deterministic templates —
# an unreadable field must become an explicit ask, never a guess).
_FIELD_LABELS = {
    "strength": "strength (e.g. 500 mg)",
    "dose": "dose (how much per intake)",
    "frequency": "frequency (how often it is taken)",
    "duration": "duration (how long the course lasts)",
    "instructions": "instructions written below the drug",
}

# Placeholder drug-name keys a model may emit instead of a readable name.
# Any such entry is dropped from the result and recorded as an explicit
# limitation — silence would read as "no medication", a false negative with
# real safety consequences.
_PLACEHOLDER_NAMES = frozenset(
    {
        "",
        "unknown",
        "unknown_medication",
        "unreadable",
        "illegible",
        "unclear",
        "n/a",
        "na",
        "none",
        "null",
        "not_legible",
    }
)

_IDENTITY_KEYS = frozenset({"patient", "patient_name", "prescriber", "doctor", "physician"})


@dataclass
class PrescriptionResult:
    """Transcribed medications from one prescription image.

    ``medications`` maps the transcribed drug name to its fields; every
    field value is a string or None (unreadable). ``uncertain`` and
    ``limitations`` are derived during parsing and drive the downstream
    safety layers exactly like the clinical-assessment result's do.
    """

    medications: dict[str, dict[str, str | None]] = field(default_factory=dict)
    limitations: list[str] = field(default_factory=list)
    uncertain: bool = False
    raw: str = ""  # original JSON, kept for the audit trail

    def to_dict(self) -> dict:
        """Wire shape: the medications contract plus derived clarifications.

        ``medications`` keeps the exact enforced transcription contract; the
        sibling ``clarifications`` list is generated here (never by the
        model) and drives both the frontend's ask-me prompts and the
        synthesis instruction to request the missing details.
        """
        return {"medications": self.medications, "clarifications": self.clarifications}

    @property
    def drug_names(self) -> list[str]:
        return list(self.medications)

    @property
    def clarifications(self) -> list[str]:
        """One targeted ask per unreadable piece of information.

        Derived purely from null fields / dropped placeholders — never from
        model introspection — so the asks can never invent uncertainty that
        is not structurally present.
        """
        asks: list[str] = []
        for name, entry in self.medications.items():
            missing = [field for field in _MEDICATION_FIELDS if not entry.get(field)]
            if missing:
                readable = ", ".join(_FIELD_LABELS[field] for field in missing)
                asks.append(f"{name}: could not read the {readable} — ask the user to read it from the label.")
        if not self.medications:
            asks.append(
                "No medications were readable from this document — ask the user "
                "for a sharper, well-lit photo or to type the medicines out."
            )
        return asks


def _extract_json_object(raw: str) -> dict:
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match is None:
        raise ValueError("No JSON object found in prescription output")
    return json.loads(match.group(0))


def _clean_field(value: object) -> str | None:
    """Coerce one medication field to a clean string or None.

    Numbers become their string form ("2" stays usable); booleans/objects/
    arrays are not transcription content and degrade to None rather than a
    mangled claim.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        cleaned = value.strip()
        lowered = cleaned.lower()
        if not cleaned or lowered in {"null", "none", "n/a", "na", "-"}:
            return None
        return cleaned
    return None


def _normalize_entry(entry: object) -> dict[str, str | None] | None:
    """Normalize one medication entry to the five-field contract shape."""
    if isinstance(entry, dict):
        return {name: _clean_field(entry.get(name)) for name in _MEDICATION_FIELDS}
    # A bare string means only the name was legible; keep the name, no fields.
    if isinstance(entry, str):
        return {name: None for name in _MEDICATION_FIELDS}
    return None


def _entries_from(data: dict) -> tuple[dict[str, dict[str, str | None]], bool]:
    """Extract (medications, contract_key_present).

    Primary shape: ``{"medications": {name: {...}}}``. A model that ignored
    the map constraint and emitted a list of name-bearing objects is folded
    back into the map so the contract survives upstream drift.
    """
    raw_meds = data.get("medications")
    if raw_meds is None:
        return {}, False
    meds: dict[str, dict[str, str | None]] = {}
    if isinstance(raw_meds, dict):
        source = raw_meds.items()
    elif isinstance(raw_meds, list):
        source = []
        for item in raw_meds:
            if not isinstance(item, dict):
                continue
            name = next(
                (
                    item.get(key)
                    for key in ("name", "drug", "medication", "medication_name")
                    if isinstance(item.get(key), str) and item.get(key).strip()
                ),
                None,
            )
            if name is not None:
                source.append((str(name), item))
    else:
        return {}, True

    for name, entry in source:
        normalized = _normalize_entry(entry)
        if normalized is None:
            continue
        key = str(name).strip()
        if key.lower() in _PLACEHOLDER_NAMES:
            continue
        meds.setdefault(key, normalized)
    return meds, True


def parse_prescription_result(raw: str) -> PrescriptionResult:
    """Parse the model's constrained JSON into a typed result.

    Tolerates code fences. Invalid JSON raises ValueError so the dispatcher's
    fault-isolation boundary degrades to the addon's unavailable reply
    instead of trusting prose.
    """
    data = _extract_json_object(raw)
    # Identity keys are outside the contract; drop them wherever they appear.
    for identity in _IDENTITY_KEYS:
        data.pop(identity, None)

    medications, present = _entries_from(data)
    limitations: list[str] = []

    if not present:
        limitations.append(
            "The transcription contained no medications section — nothing "
            "could be read from this image."
        )
        return PrescriptionResult(
            medications={},
            limitations=limitations,
            uncertain=True,
            raw=raw,
        )

    # Placeholder detection ran inside _entries_from; recover whether anything
    # was dropped so the reply can say so explicitly.
    raw_names: set[str] = set()
    raw_meds = data.get("medications")
    if isinstance(raw_meds, dict):
        raw_names = {str(k).strip().lower() for k in raw_meds}
    elif isinstance(raw_meds, list):
        raw_names = {
            str(
                next(
                    (
                        item.get(k)
                        for k in ("name", "drug", "medication")
                        if isinstance(item, dict) and isinstance(item.get(k), str)
                    ),
                    "",
                )
            ).strip().lower()
            for item in raw_meds
            if isinstance(item, dict)
        }
    dropped = raw_names & _PLACEHOLDER_NAMES
    if dropped:
        limitations.append(
            "Some entries could not be read reliably and were omitted "
            "rather than guessed."
        )

    if not medications:
        limitations.append(
            "No medication entries could be read from this image."
        )

    uncertain = not medications or bool(dropped)
    return PrescriptionResult(
        medications=medications,
        limitations=limitations,
        uncertain=uncertain,
        raw=raw,
    )
