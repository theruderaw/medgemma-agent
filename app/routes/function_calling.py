import json
from dataclasses import dataclass
from enum import Enum

from ..features import registry as feature_registry


class RouteCategory(str, Enum):
    GENERAL = "general"
    SYMPTOM_RELATED = "symptom_related"
    EMERGENCY = "emergency"


@dataclass
class RouteDecision:
    category: RouteCategory
    reason: str | None = None
    # Feature selected by this decision. Defaults to the clinical-assessment
    # tool name so directly-constructed SYMPTOM_RELATED decisions (e.g. the
    # image override) still resolve to a registered feature; GENERAL turns
    # never dispatch through it.
    feature_name: str | None = "call_medical_specialist"


def parse_tool_calls(tool_calls: list[dict]) -> RouteDecision:
    """Interpret the model's tool_calls into a routing decision.

    A tool call naming any registered feature yields SYMPTOM_RELATED (with
    that feature's name); anything else is GENERAL. EMERGENCY is never
    produced here — it is owned exclusively by the independent hardcoded
    safety check.
    """
    for call in tool_calls or []:
        function = call.get("function") or {}
        name = function.get("name")
        if feature_registry.get(name) is None:
            continue
        try:
            arguments = json.loads(function.get("arguments") or "{}")
        except json.JSONDecodeError:
            arguments = {}
        return RouteDecision(
            RouteCategory.SYMPTOM_RELATED,
            arguments.get("reason"),
            feature_name=name,
        )
    return RouteDecision(RouteCategory.GENERAL)
