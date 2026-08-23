# PROGRESS.md — Implementation Checklist

**How to use this file (read this part every time):**
1. Read `00-overview.md` first for context.
2. Read this file to find the first unchecked box — that's where you resume.
   Don't re-do checked items, and don't skip ahead past an unchecked one.
3. Do the work for that item only, in its corresponding step doc.
4. Before ending your turn, check the box(es) you completed, fill in the
   `Notes` line under that step if anything deviated from the doc, and
   update `Current status` at the top.
5. If you had to stop mid-step (partial work), leave the box unchecked but
   add a `Notes` line describing exactly what's done and what's left, so the
   next session doesn't have to rediscover it.
6. Never check a box unless `pytest` passes at that point (except where a
   step doc explicitly says otherwise).

---

## Current status

- **Active step:** Step 5 complete (with documented deviations) — only final
  sign-off remains, blocked on the broken integration suite
- **Post-step-5 additions (2026-08-23):** routing fix for contextual medication
  mentions (tool description + router prompt now prefer specific lookups);
  frontend fully rewritten (lib/hooks/ui/chat/addons/logs/layout structure,
  clinical dark tokens); persistent event timelines — `messages.turn_id`
  column + migration `b91c4de2f7a3`, history endpoint returns `turn_id`,
  restore joins `/v1/audit` by turn, timeline expansion state hoisted into the
  conversation reducer; new `GET /v1/sessions/recent` endpoint + "Recent"
  chat-switcher dropdown in the header.
- **Last updated by:** ox-alpha session, 2026-08-23
- **Blockers / open questions:** the integration suite is RED (~20 failures:
  jobs never complete under the fake-Ollama worker; root cause not yet fixed).
  Per user decision, test repairs are delegated elsewhere ("I'll get the
  tests from Claude") and Step 5 was verified with a live-model smoke suite
  (`scripts/smoke_suite.py`) instead of pytest. Steps 3–5 changes are
  uncommitted (user has not requested a commit).

---

## Step 0 — Cleanup (`01-step0-cleanup.md`)
- [x] 0.1 Repo import/dependency map produced
- [x] 0.2 Dead code / unused imports removed
- [x] 0.3 Naming consistency pass done (incl. `app/routes/__init__.py` docstring)
- [x] 0.4 Type hints / docstrings filled in
- [x] 0.5 Test-coverage-by-pipeline-path list produced
- [x] 0.6 Config/settings naming convention documented
- [x] `pytest` green, no behavior changes in diff
- [x] `CLEANUP_NOTES.md` written

**Notes:** Baseline 35 passed → final 35 passed. Import map kept in gitignored
`maps/repo-import-map.md`. Ruff (installed into `.venv`) found zero unused
imports; removals were unconsumed `__init__` re-exports only (rationale in
CLEANUP_NOTES §0.2). One flagged deviation: one-line fix in
`app/main.py::queued_chat` passing `path=result.path` on the sync emergency
response — code now matches the documented API contract (`emergency_override`
was silently `null` before); caught by the new live-model smoke script
`scripts/smoke_live.py`, which passed against the real Ollama stack. Coverage
gap for Step 2: no test triggers the `enforce_safety_invariants`
`safety_invariant` event path — add a regression test before refactoring
dispatch.

---

## Step 1 — Feature Interface & Registry (`02-step1-feature-interface.md`)
- [x] 1.1 `app/features/base.py` created (`SafetyProfile`, `ToolSchema`, `Feature`)
- [x] 1.2 `app/features/registry.py` created (`register`, `get`, `enabled_features`, `tool_schemas`)
- [x] 1.3 Confirmed `app/services/chat.py` untouched, package imports cleanly
- [x] 1.4 Scratch/dummy feature used to validate interface, then deleted
- [x] `pytest` green, zero behavior change

**Notes:** Step 1 complete. `app/features/` created, interface and registry implemented. Verified via scratch script (deleted) and `pytest` (all 35 passed). No behavior changes.

---

## Step 2 — Migrate Existing Specialist (`03-step2-migrate-specialist.md`)
- [x] 2.1 `app/features/clinical_assessment.py` created, registered
- [x] 2.2 `SPECIALIST_TOOL` removed from `app/prompts/routing.py` (re-export checked via grep)
- [x] 2.3 `run_chat_turn` dispatches via `feature_registry.tool_schemas()`
- [x] 2.3a `RouteDecision.feature_name` added, `parse_tool_calls` generalized
- [x] 2.3b specialist call site uses `feature.system_prompt` / `feature.parse()` / `feature.context_for()`
- [x] 2.4 Regression check: response/audit JSON shape identical before/after
- [x] Any missing test coverage found in Step 0 §0.5 added before refactor
- [x] `pytest` green

**Notes:** The Step 0 §0.5 gap was closed FIRST (`test_safety.py::
TestSafetyInvariants::test_emergency_triage_cannot_be_downgraded`, triage
EMERGENCY + non-template draft → `safety_invariant` / `emergency_bypass`
event), then the dispatch refactor. Tool schema sent to the router verified
byte-identical to the old `SPECIALIST_TOOL`. Deviations from the doc:
(1) `SPECIALIST_FORMAT` stayed in `app/prompts/specialist.py` — it is the
LLM transport contract consumed by `llm/client.py::specialist_stream` and
`tests/integration/fake_ollama.py`; moving it would have created an
`llm → features` upward dependency. It moves when `specialist_stream`
becomes feature-parameterized (Step 3+). (2) `RouteDecision.feature_name`
defaults to `"call_medical_specialist"` so the image-override construction
site needed no change; `parse_tool_calls` fills the matched registered name.
(3) Added a fail-fast `ValueError` at dispatch if `registry.get()` returns
None (unreachable today, prevents silent AttributeError in future steps).
Suite now 36 passed (35 baseline + 1 new).

---

## Step 3 — New Add-on Features (`04-step3-new-addons.md`)
- [x] 3.1 `app/features/symptom_triage.py` — existing triage wrapped as a feature
- [x] 3.1a Always-on `triage=True` flag path confirmed untouched
- [x] 3.2 `app/features/medication_interaction.py` (optional — mark N/A if skipped)
- [x] 3.2a Curated dataset added under `app/features/data/`, LLM only phrases, never originates claims
- [ ] 3.3 `app/features/lab_value_interpreter.py` — **N/A, skipped** (doc: #2 OR #3)
- [x] 3.4 All new features registered in `app/features/__init__.py`
- [x] 3.5 Integration tests added per new feature (incl. "no data" branch for medication feature)
- [x] `pytest` green including new tests

**Notes:** Suite 36 → 42 passed. Deviations / interface decisions: (1) The
Feature protocol was completed ONCE (the doc's sanctioned "revisit the
interface" path): added `model_setting` + `format_schema` members;
`llm.specialist_stream` gained an optional `output_format` param (default
keeps SPECIALIST_FORMAT); `run_chat_turn` resolves model/format from the
selected feature. Required because a router-selected triage must be
constrained to TRIAGE_FORMAT, not the hardcoded specialist schema. (2)
Invariant inputs read defensively (`uncertain`, `body_part_unknown`,
`limitations`) since feature results are heterogeneous dataclasses.
(3) Medication deviates from the doc's literal "extract drugs from tool-call
arguments": extraction happens in the streamed stage via
MEDICATION_QUERY_FORMAT because dispatch never hands tool args to features;
dataset still originates every claim and the unknown-pair branch yields the
explicit no-data context (unit-tested). (4) Audit event module stays
"specialist"/"specialist_output" for all streamed features to preserve the
audit JSON shape; per-feature module naming deferred to Step 5. (5)
`fake_ollama.py` extended: configurable router tool name + medication-format
branch + `calls("medication")`.

---

## Step 4 — Per-Feature Safety Profiles (`05-step4-safety-profiles.md`)
- [x] 4.1 `app/safety/invariants.py` and `app/safety/output.py` read fully, `violations`/`actions` pattern confirmed
- [x] 4.2 `safety_profile` param added with `None` default, verified behavior-neutral
- [x] 4.3 Additive profile-driven disclaimer logic added
- [x] 4.4 `run_chat_turn` passes `feature.safety_profile` through
- [x] 4.5 Test: high-disclaimer feature gets extra note, low-disclaimer doesn't
- [x] 4.5a Test: emergency floor fires regardless of feature/profile (explicit, high priority)
- [x] `pytest` green

**Notes:** Implemented in four verified stages (42 → 42 → 42 → 46 passed).
(4.2) Signature-only first: `safety_profile: SafetyProfile | None = None` on
`enforce_safety_invariants` + `run_output_guard`; suite confirmed unchanged
before any logic landed. Doc snippet says `EnforcedResult`; kept the real
class name `EnforcedResponse`. (4.3) invariants: `disclaimer_level == "high"`
→ append `PROFESSIONAL_REVIEW_NOTE` via the existing `add()` helper
(violation `profile_professional_review`, action
`append_professional_review_note`) — placed after the emergency early-return,
so the floor's replacement text is never touched by a profile. output guard:
`requires_professional_review` note fires ONLY when the guard already found
violations and urgency is not EMERGENCY — an always-on trigger would have
broken the two existing tests asserting no `output_guardrail` event on clean
specialist turns, and would also contradict the default-profile regression
guarantee (`SafetyProfile.requires_professional_review` defaults to True).
Note constant lives in `invariants.py`, imported by `output.py` (no cycle;
`safety` → `features.base` is a leaf import). (4.4) chat.py hoists
`feature = None` above the dispatch branch and passes
`feature.safety_profile if feature else None` at both call sites.
Observable effect on existing flows: specialist turns now append the review
note and record one extra `safety_invariant` audit event — verified every
existing assertion is subset/substring-based, so all 42 stayed green
unchanged. (4.5/4.5a) New `TestSafetyProfiles` (4 tests): medication turn
gets note + recorded violation/action; symptom-triage turn gets neither;
red-flag message short-circuits before routing even when the router is set
to select the strictest-profile feature (zero model calls); structured
EMERGENCY triage + high-profile feature → template replaces draft and NO
profile note is appended to it.

**Notes:**

---

## Step 5 — API, DB, Frontend Toggles (`06-step5-api-db-frontend.md`)
- [x] 5.1 Persistence scope decided (session-scoped vs global default) and documented here
- [x] 5.2 Alembic migration for `feature_settings` written, `alembic upgrade head` runs clean
- [x] 5.3 `app/features/settings.py` created; `enabled_features(session_id=...)` respects stored state
- [x] 5.3a All call sites of `enabled_features(`/`tool_schemas(` updated to pass `session_id`
- [x] 5.4 `GET /v1/features` and `POST /v1/features/{name}` added to `app/main.py` + schemas
- [x] 5.5 Frontend settings panel added, matches existing `frontend/src` patterns
- [x] 5.5a High-`disclaimer_level` features visually distinguished in UI
- [ ] 5.6 Tests: toggle affects router tool list; emergency floor unaffected by any toggle state — **done as live smoke checks, not pytest** (see Notes)
- [ ] `pytest` green — **NOT met** (see Notes)

**Notes:** Scope decision (5.1): session-scoped toggles only — no user-account
concept exists; a missing `feature_settings` row means "enabled", only
explicit disabled rows are stored (docstring in `app/features/settings.py`).
(5.2) Migration `aa73abbdd360_add_feature_settings.py`; runs clean on API
startup via `_run_migrations()`. (5.4) Routes return 404 for unknown feature
and unknown/expired session (mirrors `reset_session`); toggles are audited
(`module="features"`, `event_type="feature_toggled"`); registry gained a
read-only `all_features()` accessor so the list endpoint can show disabled
entries. (5.5) New `FeaturesPanel.tsx` + `useFeatures.ts` hook under an
"Add-ons" header tab; optimistic toggle with rollback + error banner;
toggling disabled until a session exists. (5.5a) `disclaimer_level == "high"`
renders a persistent amber "high stakes" badge next to the feature.

Deviations from the doc: (1) **Beyond scope:** added
`GET /v1/sessions/{session_id}/messages` (full persisted conversation,
oldest-first) plus frontend history restore on load (`useChat` rehydrates
from Postgres via the localStorage session id; 404 clears the stale session),
because the user asked for chat-history-from-DB explicitly.
(2) **Verification replaced:** per user instruction ("fuck the tests do 5
smoke tests each type"), 5.6 was verified live instead of via pytest:
`scripts/smoke_suite.py` runs 7 types × 5 rounds against the real stack —
general, symptom+triage, emergency, image-attached, `/v1/triage`,
features-toggle round-trip (asserts the disabled specialist disappears from /
returns to the router's tool list via the `routing_decision` audit payload's
`tools`, plus 404 on unknown feature), and history round-trip (sent message +
assistant reply both persisted and served back). Result: every check passed
in all rounds except 3 rounds that died on **Ollama ReadTimeouts**
(model-server latency >120s × 3 Celery retries under sustained load — the
app's retry/failure path behaved as designed). `pytest` remains red from the
pre-existing harness breakage (~20 tests, jobs stuck pending); repairs
delegated per user. Frontend typechecks/builds clean (`tsc -b && vite build`);
ruff shows zero new findings vs baseline.

**Notes:** Config-naming convention (absorbed from Step 0's
`CLEANUP_NOTES.md` §0.6): `app/core/config.py` = plain class of class-level
attributes, `os.getenv` with defaults; env vars `SCREAMING_SNAKE_CASE`
mirror attribute `snake_case` exactly (`MODEL_NAME` → `model_name`);
domain prefixes group related knobs (`image_*`, `audit_*`, `job_*`, model
roles as `*_model_name`). Step 5 should add e.g. `FEATURE_SETTINGS_*` /
`feature_*` following the same pattern. No pydantic-settings — keep it that
way unless a step says otherwise. (README drift, still unfixed: README's
config table omits `MAX_HISTORY_MESSAGES`, default 40.)

---

## Final sign-off (all steps complete)
- [ ] Full `pytest` suite green — blocked: integration harness broken (~20 failures), repairs delegated per user
- [ ] Manual smoke test: general chat, symptom-related chat, image-attached chat, emergency phrase — **done via `scripts/smoke_suite.py`** (7 types × 5 rounds; all passed except 3 Ollama-ReadTimeout rounds)
- [ ] All step docs' "What NOT to do" sections re-checked against final diff (no violations introduced across the whole project, even ones from an earlier step that a later step's edits might have quietly undone)
