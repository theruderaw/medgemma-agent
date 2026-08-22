# Step 0 — Codebase Audit & Cleanup

**Goal:** leave the codebase easier to extend, with zero behavior change.
This step exists so that Steps 1–5 are adding to clean ground, not building
on top of inconsistency. This is *not* the step where you add features.

**Definition of done:** `pytest` passes with the same results as before you
started, `git diff` contains no logic changes (only moves/renames/dead-code
removal/formatting/typing/docstrings), and the app still boots (`make` target
or `uvicorn app.main:app`).

## 0.1 — Map the repo before touching anything

Produce (as a scratch file, not a deliverable) a short inventory:

```
for each top-level app/ subpackage:
  - what it owns
  - what it imports from other subpackages
  - what imports it
```

Use `grep -rn "^from \.\.|^from \." app/` and `grep -rn "^import app" app/`
to build this. You need this map to safely move code in later steps —
`app/services/chat.py` currently imports from nearly every other package
(`audit`, `core`, `llm`, `prompts`, `routes`, `safety`, `sessions`,
`specialist`, `triage`), so it is the highest-risk file to refactor and the
last one you should touch in this step.

## 0.2 — Dead code and unused imports

- Run a static check for unused imports/symbols (`ruff check app/` if ruff is
  available, otherwise manual grep for each imported name's usage count).
- Check `app/prompts/__init__.py`, `app/safety/__init__.py`, and
  `app/specialist/__init__.py` re-export lists — confirm every re-exported
  name is actually consumed somewhere outside its own package. Remove ones
  that aren't, but leave a one-line comment noting what was removed and why,
  in the PR description (not in code).
- Check `app/prompts/guard.py` and `app/prompts/base.py` for anything
  superseded by newer prompt files.

## 0.3 — Naming consistency pass

The pipeline has three "stages" with inconsistent naming across files:
router/routing, specialist, triage. Before Step 1 introduces a fourth concept
(`Feature`), make sure existing names are consistent:

- Confirm `RouteCategory`, `RouteDecision` (in `app/routes/function_calling.py`)
  are the canonical names used everywhere — grep for any local re-definitions
  or shadow variables named similarly elsewhere in the codebase and consolidate.
- Confirm `SpecialistResult` (`app/specialist/parsing.py`) is the only result
  type for the specialist stage — don't leave a second ad hoc dict-based
  representation anywhere.
- `app/routes/` currently holds function-calling/routing logic, not HTTP
  routes — HTTP routes actually live in `app/main.py`. This is confusing
  once Step 5 adds real HTTP routes under `app/routes/`. **Do not rename the
  package in this step** (that's a bigger, riskier move) — instead add a
  short module docstring to `app/routes/__init__.py` clarifying that this
  package is "LLM function-calling / routing decision logic, not HTTP
  routes," so Step 5 doesn't collide with it. Flag the eventual rename
  (`app/routes` → `app/routing`) as a note for a future step rather than
  doing it now.

## 0.4 — Type hints and docstrings

- Every public function in `app/services/`, `app/safety/`, `app/llm/`,
  `app/specialist/`, `app/triage/` should have full type hints on parameters
  and return values (most already do — fill gaps only).
  Don't add type hints that require behavior-changing coercions (e.g. don't
  add a cast that changes what value is returned).
- Any function longer than ~60 lines without a docstring explaining *why*
  (not just what) gets one. Follow the existing docstring style already used
  in `app/services/chat.py::run_chat_turn` and `app/safety/invariants.py`
  (module-level docstrings explaining intent and invariants, not just params).

## 0.5 — Test coverage check (read-only)

- List which pipeline paths in `app/services/chat.py` currently have test
  coverage under `tests/integration/` (emergency override, symptom-related
  path, general/direct path, image-attached override). Do not write new
  tests in this step — just produce the list so Step 2 knows which paths are
  protected by regression tests and which are not (the ones without coverage
  are higher-risk to refactor and should get a test *before* being touched
  in Step 2).

## 0.6 — Config and settings audit

- Open `app/core/config.py`. List every setting currently defined. Step 5
  will add feature-toggle settings here — confirm naming convention (e.g.
  `snake_case`, grouped by prefix like `specialist_model_name`,
  `triage_model_name`) so new settings match.

## What NOT to do in this step

- Do not touch `app/safety/rules.py`'s `RED_FLAG_RULES` regex list, or any
  logic inside `enforce_safety_invariants` / `run_output_guard` — these are
  safety-critical and out of scope for cleanup.
- Do not change the Celery/Redis worker flow (`app/worker.py`, `app/jobs.py`).
- Do not touch `alembic/versions/` migration files.
- Do not rename any Pydantic API schema field in `app/api/schemas.py` — that's
  a breaking API change, out of scope here.

## Deliverable

A single diff (or PR) containing only: dead code removal, naming/docstring/
type-hint fixes, and the module docstring added to `app/routes/__init__.py`.
Include the repo map from 0.1 and the test-coverage list from 0.5 as a
short `CLEANUP_NOTES.md` at the repo root (delete it once Step 2 is done and
its contents are absorbed into that step's PR description).
