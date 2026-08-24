"""Contract types every addon implements, owned by the neutral registry layer.

This module imports nothing from the rest of the application: it is the
stable boundary both sides depend on. Addons implement ``Addon``; the
runtime dispatches against it without ever importing an addon.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class SafetyProfile:
    """Per-addon safety configuration consumed by the safety layers."""
    requires_professional_review: bool = True
    disclaimer_level: str = "standard"  # "standard" | "high"


# Reply used when a routed addon fails mid-turn and defines no specific
# ``unavailable_reply`` of its own. Worded conservatively so it survives the
# safety invariant/guard layers unchanged for any addon type.
DEFAULT_UNAVAILABLE_REPLY = (
    "This check is temporarily unavailable, so I can't complete it right "
    "now. Please consult a pharmacist or clinician in the meantime."
)


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


class Addon(Protocol):
    """A pluggable capability the router can dispatch to.

    Structural interface: addons implement this shape without inheriting
    anything. The runtime probes optional hooks dynamically and falls back
    to the standard LLM pipeline when they are absent.
    """

    name: str                      # matches ToolSchema.name, used for routing
    tool_schema: ToolSchema
    system_prompt: str
    safety_profile: SafetyProfile
    # Settings attribute name holding the model that runs this addon's
    # streamed stage (resolved by the dispatcher via getattr(settings, ...)).
    model_setting: str
    # Format-constrained JSON schema for the streamed stage. The constraint
    # rides on the model call so parse() always receives the expected shape.
    format_schema: dict[str, Any]

    def parse(self, raw_model_output: str) -> Any:
        """Parse raw model output into this addon's structured result type."""
        ...

    def context_for(self, result: Any, **kwargs: Any) -> str | None:
        """Build the system-prompt context string injected before final
        synthesis."""
        ...


# Optional capability hooks — all of the following are OPTIONAL members an
# addon may define. The dispatcher probes them via getattr() and falls back
# to the standard LLM pipeline when absent, so existing addons need none of
# them:
#
# deterministic_extract(text: str, history: list[dict]) -> Any | None
#     Deterministic fast-path for the extraction stage. When it returns a
#     result, the streamed specialist LLM call is skipped entirely; returning
#     None falls through to the LLM stage.
# deterministic_reply(result: Any) -> str | None
#     Deterministic final wording for the addon's result (e.g. templated
#     dataset-backed claims). A returned string replaces LLM synthesis; safety
#     invariants and output guardrails still run over it.
# route_trigger(text: str, history: list[dict]) -> bool
#     Conservative deterministic routing claim. Only ever consulted when the
#     router produced a GENERAL decision; firing forces dispatch to the
#     addon (recorded as keyword_override).
# unavailable_reply: str
#     Reply served when the addon raises mid-turn (fault-isolation
#     boundary). Defaults to DEFAULT_UNAVAILABLE_REPLY.
# accepts_images: bool
#     Capability flag for the dispatcher's image-override path: an attached
#     image is routed to the first ENABLED addon declaring True. Absent or
#     falsy means the addon never receives image bytes.
