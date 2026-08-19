CLINICAL_KEYWORDS = (
    "pain",
    "hurts",
    "symptom",
    "fever",
    "headache",
    "bleeding",
    "swelling",
    "nausea",
    "cough",
)


def should_route_to_specialist(message: str) -> bool:
    """Naive keyword router.

    Misfires, misses, and unnecessary triggers are expected at this stage; the
    goal is to prove the specialist-model call pattern works end-to-end.
    """
    text = message.lower()
    return any(keyword in text for keyword in CLINICAL_KEYWORDS)