"""Triage urgency enum and result parsing/validation."""

from .parsing import TriageResult, Urgency, parse_triage_result

__all__ = [
    "TriageResult",
    "Urgency",
    "parse_triage_result",
]
