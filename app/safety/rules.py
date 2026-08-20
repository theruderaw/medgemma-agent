import re

EMERGENCY_RESPONSE = (
    "This may be a medical emergency ({category}). Please stop and call your "
    "local emergency number (for example 911) or go to the nearest emergency "
    "department immediately. Do not wait for symptoms to worsen."
)

RED_FLAG_RULES: tuple[tuple[str, str], ...] = (
    ("chest pain", r"\bchest\s+(pain|pressure|tightness)|\bheart attack\b"),
    ("breathing difficulty", r"\bcannot?\s+breathe\b|can'?t\s+breathe|short(?:ness)?\s+of\s+breath|difficulty\s+breathing|struggl\w*\s+to\s+breathe"),
    ("stroke signs", r"(facial|face)\s+(is\s+)?droop\w*|slurred\s+speech|slurring|sudden\s+weakness|numbness\s+on\s+one\s+(side|arm|leg)|one-?sided\s+weakness"),
    ("suicidal ideation", r"kill\s+myself|suicid\w*|want\s+to\s+die|end\s+my\s+life|take\s+my\s+life"),
    ("severe bleeding", r"severe\s+bleeding|heavy\s+bleeding|bleeding\s+(heavily|profusely|uncontrollably)|uncontrollable\s+bleeding"),
    ("anaphylaxis signs", r"anaphylaxis|(throat|tongue)\s+(is\s+)?(swelling|closing)|swelling\s+of\s+the\s+(throat|tongue)"),
    ("seizure", r"\bseizure\b|convuls\w*"),
    ("unconsciousness", r"unconscious|passed\s+out|fainted|blacked\s+out"),
)


def detect_emergency(text: str) -> str | None:
    """Deterministic red-flag check on raw user text.

    Returns the matched category name or None. Must never depend on model
    output, routing decisions, or confidence.
    """
    lowered = text.lower()
    for category, pattern in RED_FLAG_RULES:
        if re.search(pattern, lowered):
            return category
    return None