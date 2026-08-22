"""Output guardrails (spec 8.1).

Every outgoing response is judged by the small guard model
(``GUARD_MODEL_NAME``, default qwen3:0.6b) against five violation
categories: definitive diagnostic claims, missing disclaimers,
emergency-path bypasses, contradictions with structured triage, and unsafe
wording. Verdicts map to deterministic fixes (append a fixed safety note or
replace the response with the emergency directive) so the model decides
*whether* something is wrong, never *how* to fix it.

A deterministic emergency floor runs before the model call: an
emergency-urgency turn whose draft is not the hardcoded emergency template
is replaced unconditionally, even if the guard model is unreachable.
"""

import json
import re
from dataclasses import dataclass, field

import httpx

from ..core.config import settings
from ..core.logging import get_logger
from ..llm import llm
from ..triage import Urgency
from .rules import EMERGENCY_RESPONSE, detect_emergency

logger = get_logger("app.safety.output")

DISCLAIMER = (
    "I'm not a diagnostic tool and this isn't medical advice — please "
    "consult a qualified healthcare professional about your symptoms."
)
ESCALATION_NOTE = (
    "Some of what you described can be more serious than it looks. If "
    "symptoms worsen or persist, seek medical care promptly; call your "
    "local emergency number for anything severe."
)
DIAGNOSTIC_CAUTION = (
    "To be clear: nothing here is a diagnosis — only a clinician who can "
    "examine you can determine what's actually going on."
)
MEDICATION_CAUTION = (
    "Please don't start, stop, or change any medication based on this chat; "
    "a doctor or pharmacist should confirm dose and interactions."
)

_FLAG_KEYS = (
    "diagnostic_claim",
    "missing_disclaimer",
    "emergency_bypass",
    "triage_contradiction",
    "unsafe_wording",
)

_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


@dataclass
class GuardedResponse:
    """Outcome of the output-guardrail pass.

    ``violations`` lists rule ids that fired, ``actions`` the deterministic
    fixes applied. ``text`` is the final text to send.
    """

    text: str
    violations: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)


def parse_guard_verdict(raw: str) -> dict[str, bool]:
    """Parse the guard model's JSON verdict into a flag mapping.

    Tolerates markdown code fences and surrounding prose; unknown keys are
    ignored and missing flags default to False.
    """
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    match = _JSON_OBJECT_RE.search(text)
    if match is None:
        raise ValueError("No JSON object found in guard verdict")
    data = json.loads(match.group(0))
    return {key: bool(data.get(key)) for key in _FLAG_KEYS}


def _emergency_text(message: str) -> str:
    category = detect_emergency(message) or "possible medical emergency"
    return EMERGENCY_RESPONSE.format(category=category)


async def run_output_guard(
    text: str,
    *,
    urgency: Urgency | None,
    message: str,
) -> GuardedResponse:
    """Judge a draft reply and apply deterministic fixes.

    Fail-open by design: if the guard model errors or returns an
    unparseable verdict, the draft passes through unchanged (the
    deterministic emergency floor has already run at that point).
    """
    violations: list[str] = []
    actions: list[str] = []
    notes: list[str] = []

    if urgency is Urgency.EMERGENCY:
        expected = _emergency_text(message)
        if text.strip() != expected.strip():
            logger.info("guard.floor.emergency_replacement")
            return GuardedResponse(
                text=expected,
                violations=["emergency_bypass"],
                actions=["replace_emergency_response"],
            )

    # Deterministic pre-gate: chit-chat turns (no triage result) and very
    # short replies are the dominant false-positive class for the small
    # guard model — skip the LLM call entirely for them.
    if urgency is None or len(text.strip()) < settings.guard_min_chars:
        logger.info(
            "guard.gate.skipped",
            urgency=urgency.value if urgency is not None else None,
            chars=len(text.strip()),
        )
        return GuardedResponse(text=text, violations=violations, actions=actions)

    try:
        raw = await llm.guard(
            message=message,
            urgency=urgency.value if urgency is not None else "none",
            response=text,
        )
        verdict = parse_guard_verdict(raw)
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        logger.warning("guard.verdict_unavailable", error=repr(exc))
        return GuardedResponse(text=text, violations=violations, actions=actions)

    def add_note(violation: str, action: str, note: str) -> None:
        violations.append(violation)
        if note not in notes:
            notes.append(note)
            actions.append(action)

    if verdict["diagnostic_claim"]:
        add_note("diagnostic_claim", "append_diagnostic_caution", DIAGNOSTIC_CAUTION)
    if verdict["unsafe_wording"]:
        add_note("unsafe_wording", "append_medication_caution", MEDICATION_CAUTION)
    if verdict["triage_contradiction"] and urgency in (Urgency.URGENT, Urgency.EMERGENCY):
        add_note("triage_contradiction", "append_escalation_note", ESCALATION_NOTE)
    if verdict["missing_disclaimer"] and urgency is not None:
        add_note("missing_disclaimer", "append_disclaimer", DISCLAIMER)
    if verdict["emergency_bypass"] and urgency is not Urgency.EMERGENCY:
        # The deterministic floor owns true emergencies; at lower urgencies a
        # bypass verdict earns the escalation note rather than a full replace.
        add_note("emergency_bypass", "append_escalation_note", ESCALATION_NOTE)

    guarded = text
    for note in notes:
        guarded = f"{guarded}\n\n{note}"

    if violations:
        logger.info(
            "guard.applied",
            violations=violations,
            actions=actions,
            model=settings.guard_model_name,
        )
    return GuardedResponse(text=guarded, violations=violations, actions=actions)
