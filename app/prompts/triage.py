from ..triage import TriageResult, Urgency

_TRIAGE_INSTRUCTIONS = (
    "You are a medical triage classifier. Assess the urgency of the user's "
    "message and extract clinical findings. Respond with JSON only:\n"
    "{{\n"
    '  "urgency": "emergency" | "urgent" | "routine" | "self_care",\n'
    '  "red_flags": ["life-threatening findings that require immediate care"],\n'
    '  "text_findings": ["clinical findings derived from the user text"],\n'
    '  "image_findings": ["objective observations derived from the attached image"],\n'
    '  "reasoning": "brief justification; state uncertainty explicitly when unsure"\n'
    "}\n"
    "Urgency levels:\n"
    "- emergency: immediate threat to life, limb, or vision.\n"
    "- urgent: needs professional care within hours to a day.\n"
    "- routine: needs professional care but can safely wait days.\n"
    "- self_care: safely manageable at home without a visit.\n"
    "Rules:\n"
    "- Use empty lists when there is nothing to report for a category.\n"
    "- Never invent image findings; only fill image_findings when an image is "
    "actually attached, and only describe what is visible.\n"
    "- If the image quality limits assessment, say so in reasoning."
)

TRIAGE_PROMPT = _TRIAGE_INSTRUCTIONS + "\n\nMessage: {message}"

TRIAGE_VISION_PROMPT = (
    _TRIAGE_INSTRUCTIONS
    + "\n\nAn image is attached to this message. Base image_findings strictly "
    "on what is visible in it.\n\nMessage: {message}"
)

TRIAGE_FORMAT = {
    "type": "object",
    "properties": {
        "urgency": {
            "type": "string",
            "enum": [u.value for u in Urgency],
        },
        "red_flags": {"type": "array", "items": {"type": "string"}},
        "text_findings": {"type": "array", "items": {"type": "string"}},
        "image_findings": {"type": "array", "items": {"type": "string"}},
        "reasoning": {"type": "string"},
    },
    "required": ["urgency", "red_flags", "text_findings", "image_findings", "reasoning"],
}

_TRIAGE_CALIBRATION = (
    "Calibrate your reply to this urgency level: emergency means direct the "
    "user to emergency services immediately; urgent means seek professional "
    "care within hours; routine means suggest scheduling a visit; self_care "
    "means home care is reasonable."
)


def triage_context_for(result: TriageResult) -> str:
    """Render the extended triage result as a system-context block for Qwen."""
    lines = [
        f"A triage classifier assessed this conversation as urgency level: {result.urgency.value}."
    ]
    if result.red_flags:
        lines.append(f"Red flags: {'; '.join(result.red_flags)}.")
    if result.text_findings:
        lines.append(f"Findings from the user's text: {'; '.join(result.text_findings)}.")
    if result.image_findings:
        lines.append(f"Findings from the attached image: {'; '.join(result.image_findings)}.")
    if result.reasoning:
        lines.append(f"Triage reasoning: {result.reasoning}")
    lines.append(_TRIAGE_CALIBRATION)
    return "\n".join(lines)
