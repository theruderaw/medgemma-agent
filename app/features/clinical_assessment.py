"""Clinical-assessment feature — the migrated MedGemma specialist.

The first real ``Feature``: the tool schema the router selects, the
specialist system prompt, structured-output parsing, and the synthesis
context builder, all moved verbatim from ``app/prompts/routing.py``,
``app/prompts/specialist.py``, and the glue around
``app/specialist/parsing.py``. Behavior is identical to the pre-registry
pipeline; only ownership moved.
"""

from ..specialist import SpecialistResult, parse_specialist_result
from .base import SafetyProfile, ToolSchema

_SYNTHESIS_RULES = (
    "Hard rules you MUST follow:\n"
    "- Do not state any finding or diagnosis that is not in the structured "
    "assessment above.\n"
    "- Preserve uncertainty exactly: never convert \"likely\", \"possible\", "
    "or \"unknown\" into definite claims, and never raise confidence.\n"
    "- Respect every listed limitation.\n"
    "- If no image was analyzed, never claim to see or interpret an image.\n"
    "- Never downgrade the triage urgency.\n"
    "- Reply with guidance, not a recap: do not restate the user's words or "
    "copy this assessment verbatim."
)


class ClinicalAssessmentFeature:
    name = "call_medical_specialist"
    tool_schema = ToolSchema(
        name="call_medical_specialist",
        description=(
            "Call when the user describes a health symptom or medical concern, "
            "or attaches an image of a visible symptom (rash, wound, swelling, "
            "skin change), that would benefit from a clinical specialist's "
            "assessment."
        ),
        parameters={
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "Concise summary of why specialist input is needed.",
                }
            },
            "required": ["reason"],
        },
    )
    system_prompt = (
        "You are a clinical specialist. Given a patient's description, produce a "
        "structured clinical assessment. Respond with JSON only:\n"
        "{\n"
        '  "summary": "one-sentence clinical impression in possibilities, not certainties",\n'
        '  "findings": ["observations derived from the patient text"],\n'
        '  "visual_findings": ["objective observations visible in the attached image"],\n'
        '  "body_part": {"value": "hand" | "foot" | "arm" | "leg" | "face" | '
        '"torso" | "other" | "unknown", "confidence": 0.0},\n'
        '  "red_flag_concerns": ["findings that could indicate something serious"],\n'
        '  "limitations": ["what could not be assessed and why"],\n'
        '  "uncertain": false\n'
        "}\n"
        "Rules:\n"
        "- Never give a definitive diagnosis; speak in possibilities.\n"
        "- Only fill visual_findings and body_part when an image is actually "
        "attached, and only describe what is actually visible. Never invent "
        "findings you cannot see.\n"
        "- For body_part: if the body part cannot be identified reliably from the "
        "image, use \"unknown\" — unknown is always preferable to a guess.\n"
        "- Set \"uncertain\": true whenever you cannot reach even a tentative "
        "assessment (poor image quality, ambiguous findings, insufficient "
        "information). Uncertainty must be stated, never hidden."
    )
    safety_profile = SafetyProfile(
        requires_professional_review=True,
        disclaimer_level="high",
    )

    def parse(self, raw_model_output: str) -> SpecialistResult:
        return parse_specialist_result(raw_model_output)

    def context_for(self, result: SpecialistResult, *, image_analyzed: bool) -> str | None:
        """Render the structured specialist result as a system-context block.

        The block states explicitly whether an image was analyzed so synthesis
        can never claim image visibility that did not happen.
        """
        lines = [
            (
                "A clinical specialist model produced the following STRUCTURED "
                "assessment. It is the only source of clinical findings for your reply."
            ),
        ]
        if result.summary:
            lines.append(f"Summary: {result.summary}")
        if result.findings:
            lines.append(f"Findings: {'; '.join(result.findings)}.")
        if image_analyzed:
            if result.visual_findings:
                lines.append(f"Visual findings from the attached image: {'; '.join(result.visual_findings)}.")
            else:
                lines.append("Visual findings from the attached image: none reported.")
            if result.body_part is not None:
                if result.body_part_unknown:
                    lines.append(
                        "Body part shown: UNKNOWN — it could not be identified "
                        "reliably. Do not name a specific body part."
                    )
                else:
                    confidence = (
                        f" (confidence {result.body_part.confidence:.2f})"
                        if result.body_part.confidence is not None
                        else ""
                    )
                    lines.append(f"Body part shown: {result.body_part.value}{confidence}.")
        else:
            lines.append("No image was analyzed for this turn.")
        if result.red_flag_concerns:
            lines.append(f"Red-flag concerns: {'; '.join(result.red_flag_concerns)}.")
        if result.limitations:
            lines.append(f"Limitations: {'; '.join(result.limitations)}.")
        if result.uncertain:
            lines.append(
                "The specialist marked this assessment UNCERTAIN. Your reply must "
                "remain uncertain — no definitive claims."
            )
        lines.append(_SYNTHESIS_RULES)
        return "\n".join(lines)


clinical_assessment_feature = ClinicalAssessmentFeature()
