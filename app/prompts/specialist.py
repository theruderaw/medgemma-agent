"""Wire-format schema for the specialist's format-constrained JSON output.

Consumed by ``app/llm/client.py`` (structured-output constraint) and the
integration fake. The prompt/context logic that used to live here moved to
``app/features/clinical_assessment.py`` in Step 2; this constant stays with
the LLM transport layer until ``specialist_stream`` becomes
feature-parameterized.
"""

from ..specialist import BODY_PART_VALUES

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
