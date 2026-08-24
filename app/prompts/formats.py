"""Wire-format schemas constraining the models' structured JSON output.

Consumed by ``app/llm/client.py`` and by add-ons that request their own
structured outputs. These are transport contracts, kept apart from the
assembled prompts in ``composed.py``.
"""

from ..domain.specialist import BODY_PART_VALUES
from ..domain.triage import Urgency

SPECIALIST_FORMAT = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "findings": {"type": "array", "items": {"type": "string"}},
        "visual_findings": {"type": "array", "items": {"type": "string"}},
        "body_part": {
            "type": "object",
            "properties": {
                "value": {"type": "string", "enum": list(BODY_PART_VALUES)},
                "confidence": {"type": "number"},
            },
        },
        "red_flag_concerns": {"type": "array", "items": {"type": "string"}},
        "limitations": {"type": "array", "items": {"type": "string"}},
        "uncertain": {"type": "boolean"},
    },
    "required": [
        "summary",
        "findings",
        "visual_findings",
        "red_flag_concerns",
        "limitations",
        "uncertain",
    ],
}


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


GUARD_FORMAT = {
    "type": "object",
    "properties": {
        "diagnostic_claim": {"type": "boolean"},
        "missing_disclaimer": {"type": "boolean"},
        "emergency_bypass": {"type": "boolean"},
        "triage_contradiction": {"type": "boolean"},
        "unsafe_wording": {"type": "boolean"},
        "reasoning": {"type": "string"},
    },
    "required": [
        "diagnostic_claim",
        "missing_disclaimer",
        "emergency_bypass",
        "triage_contradiction",
        "unsafe_wording",
        "reasoning",
    ],
}
