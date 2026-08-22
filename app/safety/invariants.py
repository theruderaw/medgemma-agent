"""Deterministic safety invariants (enforced outside any LLM).

These checks are application code, not prompt instructions. They run on every
draft reply before it is returned, regardless of ``OUTPUT_GUARDRAILS``:

1. Emergency floor — a structured emergency triage can never be downgraded:
   any draft that is not the hardcoded emergency template is replaced
   unconditionally.
2. Certainty inflation — when the specialist/triage reported uncertainty or
   limitations, absolutist phrasing in the draft earns a corrective note.
3. Body-part overreach — when the body part is unknown, definite body-part
   claims earn a corrective note.
4. Image visibility — a turn where no image was analyzed must not claim to
   have seen one.

The model decides *what to say*; this module decides *what may be sent*.
Every applied fix is returned as violations/actions so callers can audit it.
"""

import re
from dataclasses import dataclass, field

from ..triage import Urgency
from .rules import EMERGENCY_RESPONSE, detect_emergency

UNCERTAINTY_NOTE = (
    "Note: the clinical assessment here was inconclusive, so nothing above "
    "can be treated as certain — please treat it as tentative and confirm "
    "with a qualified healthcare professional."
)
BODY_PART_UNKNOWN_NOTE = (
    "Note: the body part shown could not be identified reliably, so nothing "
    "above should be read as a definite identification."
)
IMAGE_NOT_VIEWED_NOTE = (
    "Note: no image was actually analyzed in this conversation, so any "
    "reference above to seeing an image should be disregarded."
)

_CERTAINTY_RE = re.compile(
    r"\b(definitely|certainly|clearly|conclusively|almost\s+certainly|"
    r"without\s+doubt|it\s+is\s+certain)\b",
    re.IGNORECASE,
)

_IMAGE_CLAIM_RE = re.compile(
    r"\b((the|your|this|that|attached)\s+(image|photo|picture|x-?ray)|"
    r"i\s+can\s+see|i\s+see\s+in\s+(the|your)|looking\s+at\s+(the|your)\s+(image|photo|picture))\b",
    re.IGNORECASE,
)

_BODY_PART_CLAIM_RE = re.compile(
    r"\b(shows?|showing|appears?\s+to\s+be|looks?\s+like|is)\s+"
    r"(?:(?:definitely|certainly|almost\s+certainly|likely|probably|clearly)\s+)?"
    r"(a|an|your|the)?\s*(hand|foot|arm|leg|face|torso)\b",
    re.IGNORECASE,
)


@dataclass
class EnforcedResponse:
    """Outcome of the deterministic invariant pass.

    ``violations`` lists invariant ids that fired, ``actions`` the
    deterministic fixes applied. ``text`` is the text that may be sent.
    """

    text: str
    violations: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)


def emergency_template(message: str) -> str:
    """The exact text an emergency-urgency turn must send."""
    category = detect_emergency(message) or "possible medical emergency"
    return EMERGENCY_RESPONSE.format(category=category)


def enforce_safety_invariants(
    text: str,
    *,
    urgency: Urgency | None,
    message: str,
    specialist_uncertain: bool = False,
    limitations: list[str] | None = None,
    body_part_unknown: bool = False,
    image_analyzed: bool = False,
) -> EnforcedResponse:
    """Apply the deterministic safety invariants to a draft reply.

    Order matters: the emergency floor replaces the whole draft, so the
    phrasing checks only run for non-emergency drafts.
    """
    if urgency is Urgency.EMERGENCY:
        expected = emergency_template(message)
        if text.strip() != expected.strip():
            return EnforcedResponse(
                text=expected,
                violations=["emergency_bypass"],
                actions=["replace_emergency_response"],
            )
        return EnforcedResponse(text=text)

    violations: list[str] = []
    actions: list[str] = []
    notes: list[str] = []

    def add(violation: str, action: str, note: str) -> None:
        violations.append(violation)
        if note not in notes:
            notes.append(note)
            actions.append(action)

    uncertainty_signal = specialist_uncertain or bool(limitations) or body_part_unknown
    if uncertainty_signal and _CERTAINTY_RE.search(text):
        add("certainty_inflation", "append_uncertainty_note", UNCERTAINTY_NOTE)

    if body_part_unknown and _BODY_PART_CLAIM_RE.search(text):
        add("body_part_overreach", "append_body_part_unknown_note", BODY_PART_UNKNOWN_NOTE)

    if not image_analyzed and _IMAGE_CLAIM_RE.search(text):
        add("image_claim_without_image", "append_no_image_note", IMAGE_NOT_VIEWED_NOTE)

    guarded = text
    for note in notes:
        guarded = f"{guarded}\n\n{note}"
    return EnforcedResponse(text=guarded, violations=violations, actions=actions)
