from ..triage import TriageResult, Urgency

TRIAGE_INSTRUCTIONS = (
    "You are a medical triage classifier.\n"
    "Assess the urgency of the user's message.\n\n"
    "Urgency levels:\n"
    "- emergency: immediate threat to life, limb, or vision; emergency care now.\n"
    "- urgent: needs professional medical care within hours.\n"
    "- routine: needs professional medical care but can safely wait days.\n"
    "- self_care: safely manageable at home without a medical visit.\n\n"
    "Rules:\n"
    "- Prioritize avoiding under-escalation.\n"
    "- If potentially life-threatening symptoms are present, choose emergency.\n"
    "- Do not diagnose the condition.\n"
    "- Return JSON only.\n\n"
    'Output exactly: {"urgency":"emergency|urgent|routine|self_care"}'
)

TRIAGE_PROMPT = TRIAGE_INSTRUCTIONS + "\n\nMessage: {message}"


TRIAGE_FORMAT = {
    "type": "object",
    "properties": {
        "urgency": {
            "type": "string",
            "enum": [u.value for u in Urgency],
        },
    },
    "required": ["urgency"],
}


def triage_context_for(result: TriageResult) -> str:
    """Render the triage result for downstream synthesis."""

    lines = [
        f"Triage urgency: {result.urgency.value}.",
    ]

    if result.red_flags:
        lines.append(
            f"Red flags: {'; '.join(result.red_flags)}."
        )

    if result.text_findings:
        lines.append(
            f"Text findings: {'; '.join(result.text_findings)}."
        )

    if result.limitations:
        lines.append(
            f"Limitations: {'; '.join(result.limitations)}."
        )

    lines.append(
        "This triage result is authoritative for urgency. "
        "Do not downgrade the stated urgency."
    )

    return "\n".join(lines)