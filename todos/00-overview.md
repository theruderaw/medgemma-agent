# MedGemma Agent → Feature-Based System: Implementation Guide Set

This is a set of step-by-step docs for an implementing model (Claude, GPT, etc.)
to follow **in order**, one doc per work session. Each doc is scoped to be
completable and reviewable on its own — don't skip ahead.

## Repo context (read this first)

`medgemma-agent` is a FastAPI app that runs a medical chat pipeline:

```
user message
  → deterministic emergency regex check (app/safety/rules.py::detect_emergency)
  → optional MedGemma triage (app/services/triage.py)
  → Qwen router decides GENERAL vs SYMPTOM_RELATED via one hardcoded
    function-calling tool (app/prompts/routing.py::SPECIALIST_TOOL)
  → if SYMPTOM_RELATED: MedGemma "specialist" produces structured JSON
    clinical assessment (app/prompts/specialist.py, app/specialist/parsing.py)
  → Qwen synthesizes the final reply from specialist output
  → deterministic safety invariants (app/safety/invariants.py)
  → LLM output guardrail (app/safety/output.py)
  → response returned + audited (app/audit)
```

Core orchestration lives in **`app/services/chat.py::run_chat_turn`** — this
is the single most important function in the repo. Almost everything below
touches it eventually.

The system is already well-engineered and safety-conscious: a **deterministic,
non-LLM emergency floor** that can never be downgraded, structured JSON
outputs instead of free text, explicit uncertainty propagation, and a full
audit trail. **Do not weaken or bypass any of these guarantees** in the course
of refactoring. If a change in these guides seems to conflict with an
existing safety mechanism, stop and flag it instead of resolving it silently.

## The goal

Turn the current **single hardcoded pipeline** (one router, one specialist)
into a **feature-based system**: a registry of independent, pluggable medical
"add-ons" (symptom triage, image analysis, medication interaction checking,
lab value interpretation, ICD-10 coding, etc.) that the router can choose
between — the same shape as Claude's tool/connector model, applied to
medical reasoning instead of general tools.

## Workflow (start here every session)

1. Read this file (`00-overview.md`).
2. Open `PROGRESS.md` and find the first unchecked box. That tells you
   exactly which step doc to open and which task within it to do next —
   you should never need to re-read a step doc from the top to figure out
   where you left off.
3. Do that task, in its step doc, following that doc's own rules.
4. Check the box(es) in `PROGRESS.md`, add a `Notes` line if anything
   deviated from the doc, update `Current status`, then stop.

`PROGRESS.md` is the single source of truth for "where are we." The step
docs are the single source of truth for "how do I do this task." Don't let
either drift from the other — if a step doc turns out to need a task it
doesn't have a checklist line for, add the line to `PROGRESS.md` rather than
doing undocumented work.

## Doc order

| Doc | Purpose | Touches |
|---|---|---|
| `00-overview.md` | This file | — |
| `PROGRESS.md` | **Start-of-session checklist — read this second, every time** | — |
| `01-step0-cleanup.md` | Audit & clean the existing codebase *before* adding anything new | whole repo, read-only mostly |
| `02-step1-feature-interface.md` | Define the `Feature` interface + registry | new `app/features/` package |
| `03-step2-migrate-specialist.md` | Move the existing specialist behind the new interface (no behavior change) | `app/services/chat.py`, `app/prompts/`, `app/specialist/` |
| `04-step3-new-addons.md` | Add 2-3 new feature modules using the interface | new files under `app/features/` |
| `05-step4-safety-profiles.md` | Make safety rules per-feature instead of global | `app/safety/`, `app/features/base.py` |
| `06-step5-api-db-frontend.md` | Expose add-on management via API, DB, and frontend toggle | `app/routes/`, `alembic/`, `frontend/src` |

## Ground rules for every step

1. **Read before writing.** Open every file you're about to touch and any
   file that imports it (`grep -rn "from ..X import" app/`) before making
   changes.
2. **One doc = one PR-sized change.** Don't bleed work from doc N+1 into doc N.
3. **Never change behavior in a cleanup/refactor step.** If tests exist for a
   file, they must pass unchanged after a structural refactor. Run
   `pytest` after every doc (`pytest.ini` and `tests/` already exist).
4. **Preserve every safety mechanism exactly.** The emergency regex floor, the
   safety invariants, and the output guardrail must keep running on every
   turn, for every feature, with identical or stricter behavior — never
   looser.
5. **Preserve the audit trail.** Every new code path must call
   `audit.append(...)` (see existing calls in `app/services/chat.py`) the same
   way the current pipeline does, so nothing becomes untraceable.
6. **Match existing conventions** — dataclasses for results, `structlog` for
   logging, Pydantic for API schemas, the `violations`/`actions` pattern in
   `app/safety/invariants.py` for anything that mutates output. Don't
   introduce a second style.
