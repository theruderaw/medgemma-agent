"""Shared result contracts: typed model outputs consumed by the pipeline and add-ons."""

from .specialist import (
    BODY_PART_VALUES,
    BodyPart,
    BodyPartObservation,
    SpecialistResult,
    parse_specialist_result,
)
from .triage import TriageResult, Urgency, parse_triage_result

__all__ = [
    "BODY_PART_VALUES",
    "BodyPart",
    "BodyPartObservation",
    "SpecialistResult",
    "TriageResult",
    "Urgency",
    "parse_specialist_result",
    "parse_triage_result",
]
