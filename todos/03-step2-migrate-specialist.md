# Step 2 — Migrate the Existing Specialist Behind the Feature Interface

**Prerequisite:** Step 1 complete, `pytest` green.

**Goal:** make the current clinical-assessment specialist the **first real
`Feature`**, and make the router in `app/services/chat.py` dispatch through
the registry instead of the hardcoded `SPECIALIST_TOOL`. This is a pure
refactor: **the pipeline's behavior for existing inputs must be identical
before and after this step.** This is the riskiest step in the whole guide
set because it touches `run_chat_turn` — go slowly, and rely on the test
coverage list from Step 0 (§0.5) to know which paths need a regression test
added *before* you refactor them.

**Definition of done:** `SPECIALIST_TOOL` as a standalone hardcoded constant
is gone from the router call site (routing now uses
`registry.tool_schemas()`); the specialist's prompt/parsing/context logic
lives in `app/features/clinical_assessment.py`; `pytest` passes unchanged;
manually running a symptom-related turn and a general turn both produce the
same shape of response as before (same fields, same audit events, same
safety behavior).

## 2.1 — Create `app/features/clinical_assessment.py`

Move (don't duplicate) the following into this new file, adapted to
implement `Feature` from Step 1:

- `SPECIALIST_TOOL` from `app/prompts/routing.py` → becomes this feature's
  `tool_schema` (rename the underlying tool name only if you also update
  every reference — safest is to keep the tool name exactly
  `"call_medical_specialist"` so no prompt text describing it needs to change).
- `SPECIALIST_SYSTEM_PROMPT`, `SPECIALIST_FORMAT`, `_SYNTHESIS_RULES` from
  `app/prompts/specialist.py` → become this feature's `system_prompt` and
  internal constants.
- `parse_specialist_result` from `app/specialist/parsing.py` → becomes this
  feature's `parse()` method.
- `specialist_context_for` (wherever it's defined/imported from — check
  `app/prompts/__init__.py`) → becomes this feature's `context_for()` method.

Keep `SpecialistResult` (the dataclass) where it is in `app/specialist/parsing.py`
— there's no need to move the result type itself, only the feature glue.
`app/features/clinical_assessment.py` should import it, not redefine it.

```python
# app/features/clinical_assessment.py (shape, not full code)
from ..specialist import SpecialistResult, parse_specialist_result
from .base import Feature, SafetyProfile, ToolSchema

class ClinicalAssessmentFeature:
    name = "call_medical_specialist"
    tool_schema = ToolSchema(
        name="call_medical_specialist",
        description="...",   # verbatim from the old SPECIALIST_TOOL
        parameters={...},     # verbatim from the old SPECIALIST_TOOL
    )
    system_prompt = SPECIALIST_SYSTEM_PROMPT  # verbatim
    safety_profile = SafetyProfile(
        requires_professional_review=True,
        disclaimer_level="high",  # image + diagnostic reasoning: strictest tier
    )

    def parse(self, raw_model_output: str) -> SpecialistResult:
        return parse_specialist_result(raw_model_output)

    def context_for(self, result: SpecialistResult, **kwargs) -> str | None:
        return specialist_context_for(result, **kwargs)


clinical_assessment_feature = ClinicalAssessmentFeature()
```

Register it once, in `app/features/__init__.py`:

```python
from .clinical_assessment import clinical_assessment_feature
from . import registry

registry.register(clinical_assessment_feature)
```

## 2.2 — Update `app/prompts/routing.py`

`ROUTING_SYSTEM_PROMPT` stays — the router's job description doesn't change.
Remove `SPECIALIST_TOOL` from this file now that it lives in
`clinical_assessment.py` (re-export it temporarily from
`app/prompts/__init__.py` only if something outside `chat.py` still imports
it directly — grep first: `grep -rn "SPECIALIST_TOOL" app/`).

## 2.3 — Update `app/services/chat.py::run_chat_turn`

This is the core change. Find:

```python
routing = await llm.chat_with_tools(
    routing_messages,
    tools=[SPECIALIST_TOOL],
    ...
)
```

Replace with:

```python
from ..features import registry as feature_registry
...
routing = await llm.chat_with_tools(
    routing_messages,
    tools=feature_registry.tool_schemas(),
    ...
)
```

Then find where `decision.category is RouteCategory.SYMPTOM_RELATED` branches
into the hardcoded specialist call. **For this step only**, keep the
`RouteCategory` enum and the image-override logic exactly as-is — do not
generalize "which feature was selected" yet if it complicates the diff.
The minimal correct change is:

1. `parse_tool_calls` (in `app/routes/function_calling.py`) currently only
   recognizes `SPECIALIST_TOOL_NAME`. Generalize it to look up *any*
   registered feature name from `feature_registry`, not just the one
   hardcoded constant — this is the actual point of Step 2. Change its
   return type/shape as little as possible; e.g. add a `feature_name: str |
   None` field to `RouteDecision` alongside the existing `category`/`reason`,
   defaulting to the clinical assessment feature's name so existing callers
   that only look at `category` don't break.
2. Where `chat.py` builds `specialist_messages` and calls
   `llm.specialist_stream(...)`, look up the selected feature via
   `feature_registry.get(decision.feature_name)` and use
   `feature.system_prompt` instead of the imported `SPECIALIST_SYSTEM_PROMPT`
   constant, and `feature.parse(raw_specialist)` instead of the imported
   `parse_specialist_result(...)`.
3. Where `chat.py` calls `specialist_context_for(specialist, ...)`, call
   `feature.context_for(specialist, ...)` instead.

Everything else in `run_chat_turn` — the emergency floor, triage, image
override, safety invariants, output guardrail, audit calls — **stays exactly
as it is**. Do not touch those blocks in this step.

## 2.4 — Regression check

- Run the full `tests/integration/` suite. Every test that exercises the
  symptom-related path must still pass with identical assertions.
- If Step 0's coverage audit found a pipeline path without a test, add one
  now, before merging — this is exactly the kind of change that audit was
  meant to protect.
- Manually diff the JSON shape of a symptom-related turn's response and
  audit events before/after this change; they must be identical.

## What NOT to do in this step

- Do not add any new feature yet (that's Step 3).
- Do not change `SpecialistResult`'s fields.
- Do not change the emergency-floor, safety-invariant, or output-guardrail
  logic — only the routing/dispatch mechanism around the specialist call.
- Do not rename `RouteCategory.SYMPTOM_RELATED` — later steps may want a
  richer per-feature category, but that's out of scope here.

## Deliverable

`app/features/clinical_assessment.py` (new), updates to
`app/prompts/routing.py`, `app/routes/function_calling.py`,
`app/services/chat.py`. `pytest` green, response/audit shapes unchanged.
