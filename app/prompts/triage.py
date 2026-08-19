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
            "enum": ["emergency", "medical", "general"],
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