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

- **Active step:** Step 1 complete — next is Step 2 (`03-step2-migrate-specialist.md`, task 2.1)
- **Last updated by:** ox-alpha session, 2026-08-22
- **Blockers / open questions:** none. See `CLEANUP_NOTES.md` (delete after Step 2 absorbs it).

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
- [ ] 2.1 `app/features/clinical_assessment.py` created, registered
- [ ] 2.2 `SPECIALIST_TOOL` removed from `app/prompts/routing.py` (re-export checked via grep)
- [ ] 2.3 `run_chat_turn` dispatches via `feature_registry.tool_schemas()`
- [ ] 2.3a `RouteDecision.feature_name` added, `parse_tool_calls` generalized
- [ ] 2.3b specialist call site uses `feature.system_prompt` / `feature.parse()` / `feature.context_for()`
- [ ] 2.4 Regression check: response/audit JSON shape identical before/after
- [ ] Any missing test coverage found in Step 0 §0.5 added before refactor
- [ ] `pytest` green

**Notes:**

---

## Step 3 — New Add-on Features (`04-step3-new-addons.md`)
- [ ] 3.1 `app/features/symptom_triage.py` — existing triage wrapped as a feature
- [ ] 3.1a Always-on `triage=True` flag path confirmed untouched
- [ ] 3.2 `app/features/medication_interaction.py` (optional — mark N/A if skipped)
- [ ] 3.2a Curated dataset added under `app/features/data/`, LLM only phrases, never originates claims
- [ ] 3.3 `app/features/lab_value_interpreter.py` (optional — mark N/A if skipped)
- [ ] 3.4 All new features registered in `app/features/__init__.py`
- [ ] 3.5 Integration tests added per new feature (incl. "no data" branch for medication feature)
- [ ] `pytest` green including new tests

**Notes:**

---

## Step 4 — Per-Feature Safety Profiles (`05-step4-safety-profiles.md`)
- [ ] 4.1 `app/safety/invariants.py` and `app/safety/output.py` read fully, `violations`/`actions` pattern confirmed
- [ ] 4.2 `safety_profile` param added with `None` default, verified behavior-neutral
- [ ] 4.3 Additive profile-driven disclaimer logic added
- [ ] 4.4 `run_chat_turn` passes `feature.safety_profile` through
- [ ] 4.5 Test: high-disclaimer feature gets extra note, low-disclaimer doesn't
- [ ] 4.5a Test: emergency floor fires regardless of feature/profile (explicit, high priority)
- [ ] `pytest` green

**Notes:**

---

## Step 5 — API, DB, Frontend Toggles (`06-step5-api-db-frontend.md`)
- [ ] 5.1 Persistence scope decided (session-scoped vs global default) and documented here
- [ ] 5.2 Alembic migration for `feature_settings` written, `alembic upgrade head` runs clean
- [ ] 5.3 `app/features/settings.py` created; `enabled_features(session_id=...)` respects stored state
- [ ] 5.3a All call sites of `enabled_features(`/`tool_schemas(` updated to pass `session_id`
- [ ] 5.4 `GET /v1/features` and `POST /v1/features/{name}` added to `app/main.py` + schemas
- [ ] 5.5 Frontend settings panel added, matches existing `frontend/src` patterns
- [ ] 5.5a High-`disclaimer_level` features visually distinguished in UI
- [ ] 5.6 Tests: toggle affects router tool list; emergency floor unaffected by any toggle state
- [ ] `pytest` green

**Notes:**

---

## Final sign-off (all steps complete)
- [ ] Full `pytest` suite green
- [ ] Manual smoke test: general chat, symptom-related chat, image-attached chat, emergency phrase — all behave correctly
- [ ] All step docs' "What NOT to do" sections re-checked against final diff (no violations introduced across the whole project, even ones from an earlier step that a later step's edits might have quietly undone)
