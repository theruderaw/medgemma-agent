"""Prescription reader — MedGemma vision transcription of prescription media.

Reads a photographed/scanned prescription (image or PDF's first page) and
transcribes its medications into an enforced JSON contract (drug name keyed
map with strength/dose/frequency/duration/instructions). The transcription
is delivered to the client BOTH as a dedicated structured payload (rendered
as a card by the frontend) and phrased conversationally by the synthesis
model under strict don't-alter rules.

Deterministic layers owned here:

- Uncertainty derivation: empty maps / placeholder entries become explicit
  limitations (see ``app/domain/prescription.py``) — never silent absence.
- Interaction cross-check: every extracted drug pair is looked up in the
  curated dataset via :mod:`app.addons.medication_interaction` public
  helpers. Dataset claims ride into synthesis as authoritative context;
  pairs without a dataset row surface an explicit no-data statement.
- Identity exclusion: patient/prescriber fields are never extracted,
  logged, or phrased.

Routing behavior: this addon NEVER claims a text-only turn. Its keyword
trigger fires only when an image/PDF is actually attached
(``has_image=True``), and ``image_route_hint`` lets the dispatcher prefer it
over the clinical-assessment addon on prescription-looking uploads.
"""

import re

from ..domain.prescription import PrescriptionResult, parse_prescription_result
from ..prompts.formats import PRESCRIPTION_FORMAT
from ..prompts.loader import load_prompt
from ..registry import SafetyProfile, ToolSchema
from .medication_interaction import canonical_name, lookup_pair

# Interaction cross-check scale cap: every pair among the first N meds is
# checked; beyond that the context says explicitly that the list was
# truncated instead of silently hiding combinations.
MAX_INTERACTION_MEDS = 8

_RX_HINT_PATTERN = re.compile(
    r"\b(prescriptions?|rx|\brx\b|scrips?|medicine\s+slips?|medication\s+lists?"
    r"|meds?\s+lists?|doctor'?s\s+(?:note|slip)|pharmacy\s+slips?)\b",
    re.IGNORECASE,
)

_SYNTHESIS_RULES = (
    "Hard rules you MUST follow:\n"
    "- Your reply MUST present every transcribed medication with its "
    "readable fields, then end with the asks listed in the MUST-ask "
    "section. Never reply with disclaimers alone.\n"
    "- The structured transcription above is the ONLY source of medication "
    "information. Do not add, complete, correct, or guess any medication, "
    "strength, dose, frequency, duration, or instruction not present there.\n"
    "- Preserve illegibility exactly: fields that are null were unreadable — "
    "never fill them in from world knowledge. Instead, ask the user for "
    "every missing piece listed under the MUST-ask section; asking beats "
    "guessing.\n"
    "- Present interaction findings exactly as the curated dataset states "
    "them; do not weaken, strengthen, or extend them. Where the dataset has "
    "no entry, say plainly that nothing can be concluded either way and "
    "advise a pharmacist — never imply the combination is safe.\n"
    "- Never mention patient or prescriber identity, even if visible in the "
    "image.\n"
    "- Recommend verifying the transcription against the original "
    "prescription with a pharmacist before acting on it."
)


def _field_str(entry: dict[str, str | None], name: str) -> str:
    value = entry.get(name)
    return value if value else "unreadable"


class PrescriptionReaderAddon:
    name = "read_prescription"
    # Emitted alongside the conversational reply as {"kind": ..., "data": ...}
    # so clients can render the transcription as its own structured artifact.
    structured_kind = "prescription"
    tool_schema = ToolSchema(
        name="read_prescription",
        description=(
            "Call when the user attaches an image or PDF of a medical "
            "prescription (handwritten or printed) to read — transcribes "
            "the listed medications, doses, frequencies, durations, and "
            "instructions into a structured medication list."
        ),
        parameters={
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "What the user wants read from the prescription.",
                }
            },
            "required": ["reason"],
        },
    )
    accepts_images = True
    system_prompt = load_prompt("prescription_reading")
    safety_profile = SafetyProfile(
        requires_professional_review=True,
        disclaimer_level="high",
    )
    model_setting = "specialist_model_name"
    format_schema = PRESCRIPTION_FORMAT
    unavailable_reply = (
        "I could not transcribe the prescription right now because the "
        "reading service is temporarily unavailable. Please do not act on "
        "the prescription from memory of this attempt — verify the "
        "medications directly with your pharmacist or clinician."
    )

    def image_route_hint(self, text: str) -> bool:
        """Conservative claim used by the dispatcher's image override: does
        the message talk about reading a prescription?"""
        return bool(_RX_HINT_PATTERN.search(text or ""))

    def route_trigger(self, text: str, history: list[dict], *, has_image: bool = False) -> bool:
        """Keyword trigger, gated on an actual attachment.

        A prescription keyword without an attached document must NOT pull
        the turn away from other addons — this reader has nothing to read.
        """
        return has_image and self.image_route_hint(text)

    def parse(self, raw_model_output: str) -> PrescriptionResult:
        return parse_prescription_result(raw_model_output)

    def _interaction_lines(self, result: PrescriptionResult) -> list[str]:
        """Curated-dataset cross-check lines for the synthesis context."""
        names = result.drug_names
        truncated = len(names) > MAX_INTERACTION_MEDS
        considered = names[:MAX_INTERACTION_MEDS]

        canonical: dict[str, str] = {}
        unknown: list[str] = []
        for name in considered:
            resolved = canonical_name(name)
            if resolved is None:
                unknown.append(name)
            else:
                canonical[name] = resolved

        unique_canonical = sorted(set(canonical.values()))
        lines: list[str] = [
            "Interaction cross-check against the curated reference dataset:",
        ]
        found_any = False
        for i, a in enumerate(unique_canonical):
            for b in unique_canonical[i + 1 :]:
                entry = lookup_pair(a, b)
                if entry is None:
                    continue
                found_any = True
                lines.append(
                    f"- {a} + {b}: {entry['severity']} severity — "
                    f"{entry['effect']} Guidance: {entry['guidance']}"
                )

        checked_pairs = len(unique_canonical) >= 2
        if checked_pairs and not found_any:
            lines.append(
                f"- No interaction entries exist in the reference data for "
                f"any checked combination ({', '.join(unique_canonical)}). "
                f"This is NOT evidence of safety: advise confirming with a "
                f"pharmacist."
            )
        elif not checked_pairs:
            lines.append(
                "- Fewer than two recognizable drug names, so no pairwise "
                "interaction check was possible."
            )
        if unknown:
            shown = ", ".join(sorted(unknown))
            lines.append(
                f"- Name(s) not in the reference index ({shown}) were not "
                f"cross-checked — they may be brands or abbreviations; "
                f"recommend a pharmacist verify."
            )
        if truncated:
            lines.append(
                f"- Only the first {MAX_INTERACTION_MEDS} medications were "
                f"cross-checked; the prescription lists more."
            )
        return lines

    def context_for(self, result: PrescriptionResult, *, image_analyzed: bool, **kwargs) -> str | None:
        """Render the transcription plus deterministic cross-checks as the
        authoritative system-context block for synthesis."""
        lines = [
            (
                "A vision model transcribed the attached prescription into "
                "the following STRUCTURED medication list. It is the only "
                "source of medication information for your reply."
            ),
        ]
        if not image_analyzed:
            lines.append("NO image was actually analyzed for this request.")
        if not result.medications:
            lines.append("Transcribed medications: NONE readable.")
        else:
            lines.append("Transcribed medications:")
            for name, entry in result.medications.items():
                lines.append(
                    f"- {name}: strength {_field_str(entry, 'strength')}; "
                    f"dose {_field_str(entry, 'dose')}; "
                    f"frequency {_field_str(entry, 'frequency')}; "
                    f"duration {_field_str(entry, 'duration')}; "
                    f"instructions {_field_str(entry, 'instructions')}."
                )
        if result.clarifications:
            lines.append(
                "Missing information you MUST explicitly ask the user to "
                "supply (end your reply with these asks, one per line):"
            )
            lines.extend(f"  * {ask}" for ask in result.clarifications)
        if result.limitations:
            lines.append(f"Transcription limitations: {'; '.join(result.limitations)}.")
        if result.uncertain:
            lines.append(
                "The transcription is marked UNCERTAIN — your reply must "
                "stay uncertain and lean on professional verification."
            )
        lines.extend(self._interaction_lines(result))
        lines.append(_SYNTHESIS_RULES)
        return "\n".join(lines)


addon = PrescriptionReaderAddon()
