# Step 3 — Add New Add-on Features

**Prerequisite:** Step 2 complete, `pytest` green, router dispatches through
`feature_registry`.

**Goal:** prove the `Feature` interface actually generalizes by adding at
least one, ideally two, new add-ons. Each is a self-contained module —
implementing a second feature should require **zero changes** to
`app/services/chat.py` beyond what Step 2 already did (that's the point of
the abstraction — if you find yourself editing `chat.py` again per-feature,
Step 2's interface is under-specified and should be revisited before
continuing).

**Definition of done:** at least one new feature file exists under
`app/features/`, is registered, has its own prompt/parse/context logic, and
the router can select it independently of the clinical-assessment feature.
New tests exist under `tests/integration/` exercising it.

## 3.0 — Pick which add-ons to build first

Recommended order (easiest → hardest given existing infra):

1. **Symptom triage as a feature** — `app/triage/` and `app/services/triage.py`
   already exist and do something feature-shaped (MedGemma text triage →
   urgency + limitations). Wrapping the *existing* triage logic in the
   `Feature` interface is the lowest-risk way to validate the abstraction,
   since the model/prompt/parsing work is already done — this step is glue
   only. Do this one first.
2. **Medication interaction check** — new, needs a data source (see 3.2).
3. **Lab value interpreter** — new, structured numeric input.

Do at least #1. Do #2 or #3 if time allows; both follow the same pattern.

## 3.1 — Wrap existing triage as `app/features/symptom_triage.py`

This mirrors Step 2's migration pattern exactly, but for
`app/triage/parsing.py` + `app/services/triage.py` +
`app/prompts/triage.py`'s `triage_context_for` instead of the specialist:

```python
class SymptomTriageFeature:
    name = "run_symptom_triage"
    tool_schema = ToolSchema(
        name="run_symptom_triage",
        description=(
            "Call for a lightweight urgency read on a described symptom "
            "when a full clinical assessment isn't yet warranted — use "
            "before escalating to call_medical_specialist for ambiguous or "
            "early-stage descriptions."
        ),
        parameters={...},
    )
    system_prompt = ...  # from app/prompts/triage.py, if it defines one;
                          # otherwise this feature's prompt is the triage
                          # model's own instructions — check run_triage()
                          # in app/services/triage.py for where the prompt
                          # currently lives before assuming it's here
    safety_profile = SafetyProfile(
        requires_professional_review=False,  # advisory only, not diagnostic
        disclaimer_level="standard",
    )

    def parse(self, raw_model_output: str) -> TriageResult:
        ...  # reuse existing triage parsing

    def context_for(self, result: TriageResult, **kwargs) -> str | None:
        return triage_context_for(result)
```

**Important distinction from Step 2:** the current pipeline runs triage
*unconditionally* when `triage=True` is passed to `run_chat_turn`, entirely
outside the router's tool-calling decision (see the `if triage:` block near
the top of `run_chat_turn`, before the router call even happens). Do not
rip that out. For this step, the safest move is: keep the existing
always-on `triage` flag path exactly as it is (it's a request-level opt-in,
not a router decision), and register `SymptomTriageFeature` *only* so its
tool schema is available to the router as an option for symptom exploration
when the always-on triage path is off. If reconciling "triage as an
always-on flag" vs "triage as a router-selectable tool" turns out to be
more than a glue-level change, stop and note the conflict rather than
redesigning `run_chat_turn`'s triage flag semantics here — that's a
separate, larger decision than this guide covers.

## 3.2 — Medication interaction feature (if attempted)

`app/features/medication_interaction.py`. Key difference from the other
features: this one should **not** rely solely on LLM output for the
interaction claim itself — LLM-generated drug interaction facts are exactly
the kind of thing that needs a real source. Structure it as:

1. `parse()` extracts drug names mentioned (from the model's structured tool
   call arguments, e.g. `{"drug_a": "...", "drug_b": "..."}` — put this in
   `tool_schema.parameters`, not free text).
2. Look up the pair against a small curated interaction dataset you add
   under `app/features/data/drug_interactions.json` (a static file is fine
   for a first version — do not call an external network API from inside
   the request path without discussing rate limits/caching first).
3. Only use the LLM to phrase the *explanation* of a known interaction found
   in the dataset — never to originate the interaction claim itself.
4. If the pair isn't in the dataset, `context_for()` must return an explicit
   "no data available for this combination, consult a pharmacist" message —
   never silence into "no interaction found," which would be a false
   negative with real safety consequences.

`safety_profile = SafetyProfile(requires_professional_review=True, disclaimer_level="high")`.

## 3.3 — Lab value interpreter feature (if attempted)

`app/features/lab_value_interpreter.py`. `tool_schema.parameters` should
require structured fields (`test_name`, `value`, `unit`, optionally
`reference_range`) rather than parsing free text out of the model's tool
call reason string — structured input avoids misparsing "120" as the wrong
unit or the wrong test. Reject (via `parse()` raising, caught in `chat.py`'s
existing try/except patterns — check how `ImageValidationError` is handled
in `app/main.py` for the existing error-handling convention to match)
anything missing a required field rather than guessing.

## 3.4 — Register everything

Add each new feature's registration line to `app/features/__init__.py`
alongside the Step 2 registration. Order doesn't matter for correctness, but
group them with a comment per feature for readability.

## 3.5 — Tests

For each new feature, add an integration test under `tests/integration/`
mirroring the existing specialist/triage test structure: one test where the
router selects the feature, one where it doesn't (control case), and for the
medication feature specifically, one test for the "pair not in dataset"
path — that's the highest-consequence branch.

## What NOT to do in this step

- Don't touch the emergency floor, safety invariants, or output guardrail.
- Don't call any external network API from a feature without first checking
  `app/core/config.py` for how existing outbound calls (LLM client) handle
  timeouts/retries, and matching that pattern.
- Don't let a new feature's `parse()` silently swallow malformed model
  output — follow `parse_specialist_result`'s existing error handling in
  `app/specialist/parsing.py` as the template.

## Deliverable

One or more new files under `app/features/`, updated
`app/features/__init__.py`, new tests. `pytest` green including new tests.
