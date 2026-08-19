import json
import re

VALID_URGENCIES = ("emergency", "medical", "general")


def parse_triage_urgency(raw: str) -> str:
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
    if urgency not in VALID_URGENCIES:
        raise ValueError(f"Invalid urgency value: {urgency!r}")
    return urgency