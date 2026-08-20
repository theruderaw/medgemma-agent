from ..triage import Urgency

TRIAGE_PROMPT = (
    "Classify the urgency of this health-related message. "
    'Respond with JSON: {{"urgency": "emergency" | "medical" | "general"}}.\n\n'
    "Message: {message}"
)

TRIAGE_FORMAT = {
    "type": "object",
    "properties": {
        "urgency": {
            "type": "string",
            "enum": [u.value for u in Urgency],
        }
    },
    "required": ["urgency"],
}

TRIAGE_CONTEXT = (
    "A lightweight triage classifier assessed this conversation as urgency "
    "level: {urgency}. Calibrate your reply accordingly: emergency means the "
    "user should seek immediate care; medical means reassure and "
    "suggest next steps; general means answer normally."
)