"""Assembled prompts: template text loaded from ``templates/`` and composed.

Every prompt string the pipeline sends to a model is built here at import
time so the templates stay editable without touching call sites.
"""

from ..domain.triage import TriageResult
from .loader import load_prompt

SYSTEM_PROMPT = load_prompt("system")

TRIAGE_INSTRUCTIONS = load_prompt("triage")

TRIAGE_PROMPT = TRIAGE_INSTRUCTIONS + "\n\nMessage: {message}"

_GUARD_INSTRUCTIONS = load_prompt("guard")

GUARD_PROMPT = (
    _GUARD_INSTRUCTIONS
    + "\n\nUser message: {message}\nTriage urgency: {urgency}\nDraft reply: {response}"
)


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
