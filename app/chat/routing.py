import json
from dataclasses import dataclass
from enum import Enum

from ..registry import get as _get_addon


class RouteCategory(str, Enum):
    GENERAL = "general"
    SYMPTOM_RELATED = "symptom_related"
    EMERGENCY = "emergency"


@dataclass
class RouteDecision:
    category: RouteCategory
    reason: str | None = None
    # Addon selected by this decision. Every SYMPTOM_RELATED decision must
    # name its addon explicitly — the router's tool call, a keyword trigger,
    # or the image-override capability lookup; GENERAL decisions carry None.
    # There is deliberately no default: nothing here may privilege a
    # specific registered addon by name.
    addon_name: str | None = None


def parse_tool_calls(tool_calls: list[dict]) -> RouteDecision:
    """Interpret the model's tool_calls into a routing decision.

    A tool call naming any registered addon yields SYMPTOM_RELATED (with
    that addon's name); anything else is GENERAL. EMERGENCY is never
    produced here — it is owned exclusively by the independent hardcoded
    safety check.
    """
    for call in tool_calls or []:
        function = call.get("function") or {}
        name = function.get("name")
        if _get_addon(name) is None:
            continue
        try:
            arguments = json.loads(function.get("arguments") or "{}")
        except json.JSONDecodeError:
            arguments = {}
        return RouteDecision(
            RouteCategory.SYMPTOM_RELATED,
            arguments.get("reason"),
            addon_name=name,
        )
    return RouteDecision(RouteCategory.GENERAL)
