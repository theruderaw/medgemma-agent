import json
from dataclasses import dataclass
from enum import Enum


class RouteCategory(str, Enum):
    GENERAL = "general"
    SYMPTOM_RELATED = "symptom_related"
    EMERGENCY = "emergency"


@dataclass
class RouteDecision:
    category: RouteCategory
    reason: str | None = None


SPECIALIST_TOOL_NAME = "call_medical_specialist"


def parse_tool_calls(tool_calls: list[dict]) -> RouteDecision:
    """Interpret the model's tool_calls into a routing decision.

    Returns SYMPTOM_RELATED (with the reason) if the model requested the
    specialist tool, otherwise GENERAL. EMERGENCY is never produced here — it is
    owned exclusively by the independent hardcoded safety check.
    """
    for call in tool_calls or []:
        function = call.get("function") or {}
        if function.get("name") == SPECIALIST_TOOL_NAME:
            try:
                arguments = json.loads(function.get("arguments") or "{}")
            except json.JSONDecodeError:
                arguments = {}
            return RouteDecision(
                RouteCategory.SYMPTOM_RELATED,
                arguments.get("reason"),
            )
    return RouteDecision(RouteCategory.GENERAL)