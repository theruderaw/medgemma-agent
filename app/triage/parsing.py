import json
import re
from dataclasses import dataclass, field
from enum import StrEnum


class Urgency(StrEnum):
    EMERGENCY = "emergency"
    URGENT = "urgent"
    ROUTINE = "routine"
    SELF_CARE = "self_care"


VALID_URGENCIES = tuple(u.value for u in Urgency)


@dataclass
class TriageResult:
    """Extended triage output (Milestone 7 schema).

    Findings are kept separate by source so the response can distinguish
    what came from the user's text, what came from an attached image, and
    what the model was uncertain about (stated inside ``reasoning``).
    """

    urgency: Urgency
    red_flags: list[str] = field(default_factory=list)
    text_findings: list[str] = field(default_factory=list)
    image_findings: list[str] = field(default_factory=list)
    reasoning: str = ""

    def to_dict(self) -> dict:
        return {
            "urgency": self.urgency.value,
            "red_flags": self.red_flags,
            "text_findings": self.text_findings,
            "image_findings": self.image_findings,
            "reasoning": self.reasoning,
        }


def _extract_json_object(raw: str) -> dict:
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match is None:
        raise ValueError("No JSON object found in triage output")
    return json.loads(match.group(0))


def _string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    stripped = str(value).strip()
    return [stripped] if stripped else []


def parse_triage_result(raw: str) -> TriageResult:
    """Parse the triage model's JSON response into a typed extended result.

    Tolerates markdown code fences and surrounding prose; validates the
    urgency value against the enum.
    """
    data = _extract_json_object(raw)
    urgency_value = data.get("urgency")
    try:
        urgency = Urgency(urgency_value)
    except ValueError:
        raise ValueError(f"Invalid urgency value: {urgency_value!r}")
    return TriageResult(
        urgency=urgency,
        red_flags=_string_list(data.get("red_flags")),
        text_findings=_string_list(data.get("text_findings")),
        image_findings=_string_list(data.get("image_findings")),
        reasoning=str(data.get("reasoning") or "").strip(),
    )
