import json
import re
from enum import StrEnum


class Urgency(StrEnum):
    EMERGENCY = "emergency"
    MEDICAL = "medical"
    GENERAL = "general"


VALID_URGENCIES = tuple(u.value for u in Urgency)


def parse_triage_urgency(raw: str) -> Urgency:
    """Parse the tiny triage model's JSON response.

    Strips markdown code fences and surrounding prose, extracts the first JSON
    object, and returns the validated urgency value.
    """
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match is None:
        raise ValueError("No JSON object found in triage output")
    data = json.loads(match.group(0))
    urgency = data.get("urgency")
    try:
        return Urgency(urgency)
    except ValueError:
        raise ValueError(f"Invalid urgency value: {urgency!r}")