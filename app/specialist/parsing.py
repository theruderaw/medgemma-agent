import json
import re
from dataclasses import dataclass, field
from enum import StrEnum


class BodyPart(StrEnum):
    HAND = "hand"
    FOOT = "foot"
    ARM = "arm"
    LEG = "leg"
    FACE = "face"
    TORSO = "torso"
    OTHER = "other"
    UNKNOWN = "unknown"


BODY_PART_VALUES = tuple(bp.value for bp in BodyPart)


@dataclass
class BodyPartObservation:
    """Structured body-part identification from an image.

    ``unknown`` is a first-class answer: an unreliable guess must never be
    upgraded to a classification downstream.
    """

    value: BodyPart
    confidence: float | None = None

    def to_dict(self) -> dict:
        return {"value": self.value.value, "confidence": self.confidence}


@dataclass
class SpecialistResult:
    """Structured specialist (MedGemma) output.

    Replaces the previous free-form prose note so uncertainty, limitations,
    and image-derived findings survive into synthesis as structured data.
    """

    summary: str = ""
    findings: list[str] = field(default_factory=list)
    visual_findings: list[str] = field(default_factory=list)
    red_flag_concerns: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    uncertain: bool = False
    body_part: BodyPartObservation | None = None  # image turns only
    raw: str = ""  # original JSON, kept for the audit trail

    @property
    def body_part_unknown(self) -> bool:
        """True when no reliable body-part identification exists."""
        return self.body_part is None or self.body_part.value is BodyPart.UNKNOWN

    def to_dict(self) -> dict:
        return {
            "summary": self.summary,
            "findings": self.findings,
            "visual_findings": self.visual_findings,
            "red_flag_concerns": self.red_flag_concerns,
            "limitations": self.limitations,
            "uncertain": self.uncertain,
            "body_part": self.body_part.to_dict() if self.body_part else None,
        }

    def render(self) -> str:
        """Human-readable rendering of the structured result.

        Used for the specialist display channel and as the synthesis context;
        it never states more certainty than the structured fields carry.
        """
        lines = [f"Summary: {self.summary}" if self.summary else "Summary: none"]
        if self.findings:
            lines.append(f"Findings: {'; '.join(self.findings)}.")
        if self.visual_findings:
            lines.append(f"Visual findings from the attached image: {'; '.join(self.visual_findings)}.")
        if self.body_part is not None:
            if self.body_part.value is BodyPart.UNKNOWN:
                lines.append("Body part shown: cannot be identified reliably.")
            elif self.body_part.confidence is not None:
                lines.append(
                    f"Body part shown: {self.body_part.value} "
                    f"(confidence {self.body_part.confidence:.2f})."
                )
            else:
                lines.append(f"Body part shown: {self.body_part.value}.")
        if self.red_flag_concerns:
            lines.append(f"Red-flag concerns: {'; '.join(self.red_flag_concerns)}.")
        if self.limitations:
            lines.append(f"Limitations: {'; '.join(self.limitations)}.")
        if self.uncertain:
            lines.append(
                "Uncertainty: the specialist could not reach a confident "
                "assessment — treat everything above as tentative."
            )
        return "\n".join(lines)


def _extract_json_object(raw: str) -> dict:
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match is None:
        raise ValueError("No JSON object found in specialist output")
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


def _optional_confidence(value: object) -> float | None:
    if value is None or isinstance(value, str) and not value.strip():
        return None
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return None
    return min(max(confidence, 0.0), 1.0)


def _optional_body_part(value: object) -> BodyPartObservation | None:
    if isinstance(value, dict):
        raw_value = value.get("value")
        confidence = _optional_confidence(value.get("confidence"))
    else:
        raw_value = value
        confidence = None
    if raw_value is None:
        return None
    try:
        return BodyPartObservation(value=BodyPart(str(raw_value).strip().lower()), confidence=confidence)
    except ValueError:
        # An unrecognized body-part value degrades to unknown, never to a guess.
        return BodyPartObservation(value=BodyPart.UNKNOWN, confidence=confidence)


def parse_specialist_result(raw: str) -> SpecialistResult:
    """Parse the specialist model's JSON response into a typed result.

    Tolerates markdown code fences and surrounding prose. Invalid JSON raises
    ValueError so callers fail safely instead of trusting arbitrary prose.
    """
    data = _extract_json_object(raw)
    uncertain_raw = data.get("uncertain")
    return SpecialistResult(
        summary=str(data.get("summary") or "").strip(),
        findings=_string_list(data.get("findings")),
        visual_findings=_string_list(data.get("visual_findings")),
        red_flag_concerns=_string_list(data.get("red_flag_concerns")),
        limitations=_string_list(data.get("limitations")),
        uncertain=bool(uncertain_raw) if isinstance(uncertain_raw, bool) else str(uncertain_raw or "").strip().lower() == "true",
        body_part=_optional_body_part(data.get("body_part")),
        raw=raw,
    )
