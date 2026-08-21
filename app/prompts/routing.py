ROUTING_SYSTEM_PROMPT = (
    "You are the routing layer of a medical chat assistant. Given the "
    "conversation, decide whether the user's latest message describes a health "
    "symptom or medical concern that needs a clinical specialist's assessment.\n\n"
    "If it does, call the call_medical_specialist tool with a concise reason.\n"
    "If the message is general (greeting, chit-chat, admin question, thanks), "
    "reply directly to the user without calling any tool.\n\n"
    "An attached image is potential clinical evidence: if the user attached an "
    "image, call the specialist tool unless the turn is clearly not medical.\n\n"
    "Never attempt to handle emergencies yourself: if the user describes a "
    "life-threatening situation, still respond with clear advice to seek "
    "immediate emergency care, and do not call the specialist tool for it."
)

SPECIALIST_TOOL = {
    "type": "function",
    "function": {
        "name": "call_medical_specialist",
        "description": (
            "Call when the user describes a health symptom or medical concern, "
            "or attaches an image of a visible symptom (rash, wound, swelling, "
            "skin change), that would benefit from a clinical specialist's "
            "assessment."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "Concise summary of why specialist input is needed.",
                }
            },
            "required": ["reason"],
        },
    },
}