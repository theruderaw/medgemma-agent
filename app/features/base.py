from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class SafetyProfile:
    """Per-feature safety configuration. See Step 4 for how this is consumed."""
    requires_professional_review: bool = True
    disclaimer_level: str = "standard"  # "standard" | "high"


@dataclass(frozen=True)
class ToolSchema:
    """OpenAI-style function-calling tool definition for the router."""
    name: str
    description: str
    parameters: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class Feature(Protocol):
    """A pluggable medical capability the router can dispatch to.

    Mirrors the existing SPECIALIST_TOOL / SPECIALIST_SYSTEM_PROMPT /
    parse_specialist_result / specialist_context_for shape already used for
    the clinical-assessment path in app/prompts/specialist.py and
    app/specialist/parsing.py — this Protocol just names that shape so more
    than one feature can implement it.
    """

    name: str                      # matches ToolSchema.name, used for routing
    tool_schema: ToolSchema
    system_prompt: str
    safety_profile: SafetyProfile

    def parse(self, raw_model_output: str) -> Any:
        """Parse raw model output into this feature's structured result type."""
        ...

    def context_for(self, result: Any, **kwargs: Any) -> str | None:
        """Build the system-prompt context string injected before final
        synthesis, mirroring specialist_context_for's signature/shape."""
        ...
