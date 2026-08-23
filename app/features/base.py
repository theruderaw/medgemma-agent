from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class SafetyProfile:
    """Per-feature safety configuration. See Step 4 for how this is consumed."""
    requires_professional_review: bool = True
    disclaimer_level: str = "standard"  # "standard" | "high"


# Reply used when a routed feature fails mid-turn and defines no specific
# ``unavailable_reply`` of its own. Worded conservatively so it survives the
# safety invariant/guard layers unchanged.
DEFAULT_UNAVAILABLE_REPLY = (
    "This check is temporarily unavailable, so I can't assess this right "
    "now. Please consult a pharmacist or clinician before combining or "
    "changing any medications."
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
    # Settings attribute name holding the model that runs this feature's
    # streamed stage (resolved by the dispatcher via getattr(settings, ...)).
    model_setting: str
    # Format-constrained JSON schema for the streamed stage. The constraint
    # rides on the model call so parse() always receives the expected shape.
    format_schema: dict[str, Any]

    def parse(self, raw_model_output: str) -> Any:
        """Parse raw model output into this feature's structured result type."""
        ...

    def context_for(self, result: Any, **kwargs: Any) -> str | None:
        """Build the system-prompt context string injected before final
        synthesis, mirroring specialist_context_for's signature/shape."""
        ...


# Optional capability hooks — all of the following are OPTIONAL members a
# feature may define. The dispatcher probes them via getattr() and falls back
# to the standard LLM pipeline when absent, so existing features need none of
# them:
#
# deterministic_extract(text: str, history: list[dict]) -> Any | None
#     Deterministic fast-path for the extraction stage. When it returns a
#     result, the streamed specialist LLM call is skipped entirely; returning
#     None falls through to the LLM stage.
# deterministic_reply(result: Any) -> str | None
#     Deterministic final wording for the feature's result (e.g. templated
#     dataset-backed claims). A returned string replaces LLM synthesis; safety
#     invariants and output guardrails still run over it.
# route_trigger(text: str, history: list[dict]) -> bool
#     Conservative deterministic routing claim. Only ever consulted when the
#     router produced a GENERAL decision; firing forces dispatch to the
#     feature (recorded as keyword_override).
# unavailable_reply: str
#     Reply served when the feature raises mid-turn (fault-isolation
#     boundary). Defaults to DEFAULT_UNAVAILABLE_REPLY.
