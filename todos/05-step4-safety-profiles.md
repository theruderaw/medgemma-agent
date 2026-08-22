# Step 4 — Per-Feature Safety Profiles

**Prerequisite:** Step 3 complete, at least two features registered,
`pytest` green.

**Goal:** today, `app/safety/invariants.py` and `app/safety/output.py` apply
one global policy to every reply regardless of which feature produced it.
Make the strictness configurable per feature via the `SafetyProfile` already
defined in Step 1 (`app/features/base.py`), **without ever loosening the
current global floor** — the emergency regex check in
`app/safety/rules.py::detect_emergency` and the certainty/body-part/image
invariants in `app/safety/invariants.py` must keep running unconditionally
for every feature, every time. This step only allows *adding* stricter
behavior per feature, never opting out of the baseline.

**Definition of done:** `enforce_safety_invariants` and `run_output_guard`
accept a `safety_profile` parameter; the medication-interaction feature (if
built in Step 3) demonstrably gets an extra disclaimer that the
lower-stakes symptom-triage feature does not; every existing test still
passes because the default profile matches current global behavior exactly.

## 4.1 — Read `app/safety/invariants.py` and `app/safety/output.py` fully before changing anything

Confirm your understanding of the `violations`/`actions` pattern:
`enforce_safety_invariants` returns an object with `.text`, `.violations`,
`.actions` — every corrective change is recorded, never silent. Any new
per-feature logic you add must follow this exact pattern; don't introduce a
different return shape.

## 4.2 — Extend the function signatures, not the logic, first

```python
# app/safety/invariants.py
def enforce_safety_invariants(
    text: str,
    *,
    urgency: Urgency | None,
    message: str,
    specialist_uncertain: bool,
    limitations: list[str],
    body_part_unknown: bool,
    image_analyzed: bool,
    safety_profile: SafetyProfile | None = None,  # NEW, defaults preserve current behavior
) -> EnforcedResult:
```

With `safety_profile=None` behaving **identically** to today's code path.
Verify this with the existing test suite before adding any new branch.

## 4.3 — Add the profile-driven behavior

Only after 4.2 is verified behavior-neutral, add:

```python
if safety_profile is not None and safety_profile.disclaimer_level == "high":
    # append an additional professional-review disclaimer on top of
    # whatever the baseline invariants already produced — additive only,
    # never replacing or removing an existing note
    ...
```

Apply the same additive pattern to `run_output_guard` in
`app/safety/output.py` for `requires_professional_review`.

## 4.4 — Wire it through `app/services/chat.py`

Where `run_chat_turn` currently calls `enforce_safety_invariants(...)` and
`run_output_guard(...)`, look up the selected feature via
`feature_registry.get(decision.feature_name)` (added in Step 2) and pass
`safety_profile=feature.safety_profile if feature else None`.

## 4.5 — Regression + new coverage

- All existing tests pass with default (`None`) profile behavior unchanged.
- New test: a turn routed to the medication-interaction feature (or
  whichever feature has `disclaimer_level="high"`) contains the extra
  disclaimer text; a turn routed to the lower-stakes feature does not.
- New test: confirm the emergency floor in `detect_emergency` still fires
  and overrides output **regardless of which feature was selected or what
  its safety_profile says** — this is the one thing no profile should ever
  be able to affect. Write this test explicitly; it's the most important
  one in this step.

## What NOT to do in this step

- Do not let any `safety_profile` value skip, weaken, or short-circuit the
  emergency floor, the certainty-inflation check, the body-part check, or
  the image-visibility check — those run on every turn, every feature,
  unconditionally, before this step and after it.
- Do not remove the `None`-default code path — it's your regression safety
  net and should stay even after every feature has an explicit profile.

## Deliverable

Updated `app/safety/invariants.py`, `app/safety/output.py`,
`app/services/chat.py` wiring. New tests confirming both the additive
per-feature behavior and the untouchable global floor. `pytest` green.
