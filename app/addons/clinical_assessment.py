"""Clinical-assessment addon — the migrated MedGemma specialist.

The first real ``Addon``: the tool schema the router selects, the
specialist system prompt, structured-output parsing, and the synthesis
context builder, all moved verbatim from ``app/prompts/routing.py``,
``app/prompts/specialist.py``, and the glue around
``app/specialist/parsing.py``. Behavior is identical to the pre-registry
pipeline; only ownership moved.
"""

from ..domain.specialist import SpecialistResult, parse_specialist_result
from ..prompts.formats import SPECIALIST_FORMAT
from ..prompts.loader import load_prompt
from ..registry import SafetyProfile, ToolSchema

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


class ClinicalAssessmentAddon:
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
    accepts_images = True
    system_prompt = load_prompt("specialist_clinical")
    safety_profile = SafetyProfile(
        requires_professional_review=True,
        disclaimer_level="high",
    )
    model_setting = "specialist_model_name"
    format_schema = SPECIALIST_FORMAT

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


addon = ClinicalAssessmentAddon()
