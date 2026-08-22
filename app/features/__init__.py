from . import registry
from .base import Feature, SafetyProfile, ToolSchema
from .clinical_assessment import clinical_assessment_feature
from .medication_interaction import medication_interaction_feature
from .registry import enabled_features, get, register, tool_schemas
from .symptom_triage import symptom_triage_feature

# Clinical assessment: the migrated Step 2 specialist (diagnostic tier).
registry.register(clinical_assessment_feature)
# Symptom triage: lightweight urgency read; the always-on triage=True flag
# path is independent of this router-selectable option.
registry.register(symptom_triage_feature)
# Medication interaction: dataset-backed lookup, LLM phrases only.
registry.register(medication_interaction_feature)

__all__ = [
    "Feature",
    "SafetyProfile",
    "ToolSchema",
    "clinical_assessment_feature",
    "enabled_features",
    "get",
    "medication_interaction_feature",
    "register",
    "registry",
    "symptom_triage_feature",
    "tool_schemas",
]
