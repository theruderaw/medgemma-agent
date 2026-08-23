"""Feature package: registry + self-registration of every bundled feature.

Registration is defensive by design: a broken feature module (syntax error,
corrupt dataset, bad import) must never prevent the application from booting.
A failing feature is logged, skipped, and simply never offered as a router
tool; everything else keeps running untouched.
"""

import structlog

from . import registry
from .base import Feature, SafetyProfile, ToolSchema
from .registry import enabled_features, feature_names, get, register, tool_schemas

logger = structlog.get_logger(__name__)

_BUNDLED_FEATURES: list[tuple[str, str]] = [
    # (module, instance attribute) — clinical assessment first: the migrated
    # Step 2 specialist (diagnostic tier). Symptom triage is the lightweight
    # urgency read; the always-on triage=True flag path is independent of it.
    # Medication interaction: dataset-backed lookup, LLM phrases only.
    ("clinical_assessment", "clinical_assessment_feature"),
    ("symptom_triage", "symptom_triage_feature"),
    ("medication_interaction", "medication_interaction_feature"),
]

for _module_name, _attr_name in _BUNDLED_FEATURES:
    try:
        _module = __import__(
            f"{__package__}.{_module_name}", fromlist=[_attr_name]
        )
        registry.register(getattr(_module, _attr_name))
    except Exception:
        logger.exception("feature.registration_failed", module=_module_name)

__all__ = [
    "Feature",
    "SafetyProfile",
    "ToolSchema",
    "enabled_features",
    "feature_names",
    "get",
    "register",
    "registry",
    "tool_schemas",
]
