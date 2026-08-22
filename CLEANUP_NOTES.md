# CLEANUP_NOTES.md — Step 0 (Codebase Audit & Cleanup)

Scratch deliverable per `todos/01-step0-cleanup.md`. Delete once Step 2 is
done and its contents are absorbed into that step's PR description.

## Baseline & verification

- **Baseline before any edit:** `pytest tests/integration` → **35 passed**.
- **After cleanup:** **35 passed** (identical), imports clean, app boots.
- Live-model smoke (`scripts/smoke_live.py`, real Ollama stack): general →
  `qwen_direct`, symptom+triage → `medical_specialist`, emergency phrase →
  sync `emergency_override`. All passed.

## 0.1 Repo import map

Kept as a scratch artifact in `maps/repo-import-map.md` (gitignored).
Highlights: `services/chat.py` imports all 9 subpackages (highest-risk file);
two inverted edges exist (`prompts → {specialist, triage}`,
`llm → prompts`) that a future `Feature` registry must thread through;
`routes/` has a single consumer so its rename is low-blast-radius; no
circular imports.

## 0.2 Dead code / unused re-exports — what was removed and why

Ruff (`F` rules) found zero unused imports inside modules. All removals are
package-level re-exports in `__init__.py` files whose names had **zero
consumers outside their own package** (verified by grep over `app/`,
`tests/`, `alembic/` for both package-path and module-path imports):

- `app/audit/__init__.py`: removed `AuditLogger`, `CompositeAuditLogger`,
  `JsonFileAuditLogger`, `PostgresAuditLogger`, `build_audit_logger`
  (internal to `logger.py`; only `audit` / `trim_llm_payload` are consumed).
- `app/safety/__init__.py`: removed the note constants
  (`BODY_PART_UNKNOWN_NOTE`, `IMAGE_NOT_VIEWED_NOTE`, `UNCERTAINTY_NOTE`),
  result types (`EnforcedResponse`, `GuardedResponse`), fixed-note constants
  (`DIAGNOSTIC_CAUTION`, `DISCLAIMER`, `ESCALATION_NOTE`,
  `MEDICATION_CAUTION`), `emergency_template`, and `RED_FLAG_RULES` — all
  internal to `invariants.py` / `output.py` / `rules.py` (tests import
  `DIAGNOSTIC_CAUTION` via `app.safety.output` directly). Kept:
  `detect_emergency`, `EMERGENCY_RESPONSE`, `enforce_safety_invariants`,
  `run_output_guard`.
- `app/sessions/__init__.py`: removed `Session`, `SessionManager`,
  `SessionStore`, `PostgresSessionStore` (internal; consumers use the
  `sessions` singleton and `SessionExpiredError`).
- `app/core/__init__.py`: removed all nine re-exports — every consumer
  imports from concrete submodules (`app.core.config`, `app.core.db`, ...).
- `app/triage/__init__.py`: removed `BODY_PART_VALUES`, `VALID_URGENCIES`
  (internal to `parsing.py`). Note: `triage.BODY_PART_VALUES` is a plain
  string tuple, distinct from `specialist.BODY_PART_VALUES` (enum-derived) —
  both stay internal to their packages.
- `app/specialist/__init__.py`: removed `BodyPart`, `BodyPartObservation`
  (internal; `BODY_PART_VALUES`, `SpecialistResult`,
  `parse_specialist_result` are consumed by `prompts/` and `services/`).
- `app/routes/__init__.py`: removed `SPECIALIST_TOOL_NAME` (internal).
- `app/llm/__init__.py`: removed `ChatResult` (return type used only inside
  `client.py`; Step 2 can re-export it if the Feature interface needs it).

`prompts/guard.py` and `prompts/base.py`: fully live (guard prompt/format
consumed by `llm/client.py` + fake Ollama; `SYSTEM_PROMPT` by synthesis) —
nothing superseded, nothing removed. Cosmetic ruff findings left alone:
70 × E501 long lines (mostly prompts/regex strings where rewrapping would be
risky), 17 × W292 missing EOF newline (untouched to keep diff behavior-pure;
fixable mechanically later).

## 0.3 Naming consistency

- `RouteCategory` / `RouteDecision` defined once in
  `app/routes/function_calling.py`; no shadows or local re-definitions.
- `SpecialistResult` is the single specialist representation; audit payloads
  use its `to_dict()` serialization, not an ad-hoc dict shape.
- Added module docstring to `app/routes/__init__.py` clarifying it is LLM
  function-calling logic, not HTTP routes (HTTP lives in `app/main.py`).
- **Flagged for a future step:** rename `app/routes` → `app/routing` when
  Step 5 introduces real HTTP route modules. Single consumer today
  (`services/chat.py`) keeps blast radius small.

## 0.4 Type hints / docstrings

Gaps filled (all pre-existing code already had full hints except these):
- `llm/client.py::LLMClient.chat` — added intent docstring (only public
  client method without one).
- `llm/parsing.py::StreamExtractor.feed` / `.finish` — added docstrings
  documenting hold-back/suppression semantics.
No signature or coercion changes anywhere. Nested helpers (`record` in
`chat.py`, `add`/`add_note` in safety) intentionally left without
docstrings: private closures under 5 lines.

## 0.5 Test coverage by pipeline path (`run_chat_turn`)

| Path / stage | Covered by |
|---|---|
| Emergency floor (sync API short-circuit + worker-side) | `test_safety.py::test_red_flag_short_circuits_synchronously`, `test_floor_precedes_triage_opt_in_and_images` |
| General/direct (`qwen_direct`) | `test_chat_flow.py::test_router_declining_specialist_answers_directly`, `test_router_deliberation_never_reaches_the_user`, `test_completed_turn_persists_reply_and_result` |
| Symptom-related (`medical_specialist`, no image) | `test_job_stream.py::test_pipeline_events_replay_then_result_terminates`, `test_specialist_and_reply_tokens_stream`; `test_chat_flow.py` (path assertion) |
| Image override → specialist | `test_images.py::test_image_is_audited_and_reaches_specialist`, `test_router_cannot_drop_an_attached_image`, `test_image_without_triage_never_hits_triage_model` |
| Triage opt-in semantics | `test_triage_opt_in.py` (3 tests), `test_triage_endpoint.py` |
| Output guardrail | `test_safety.py::TestOutputGuardrails` (consulted-on-long-turns, caution-append, short-reply skip) |
| Session persistence/reset, job/SSE contract, audit API, image validation | respective test files |
| **GAP: `enforce_safety_invariants` violation path** | **no test triggers a `safety_invariant` event** (invariant text replacement / emergency-downgrade prevention untested). Add a regression test *before* Step 2 touches dispatch. |

## 0.6 Config naming convention (for Step 5 feature toggles)

`app/core/config.py` = plain class of class-level attributes, `os.getenv`
with defaults; env vars `SCREAMING_SNAKE_CASE` mirror attribute
`snake_case` exactly (`MODEL_NAME` → `model_name`); domain prefixes group
related knobs (`image_*`, `audit_*`, `job_*`, model roles as
`*_model_name`). Step 5 should add e.g. `FEATURE_SETTINGS_*` /
`feature_*` following the same pattern. No pydantic-settings — keep it that
way unless a step says otherwise.

Doc drift noted (not fixed here — README change, not code): README's config
table omits `MAX_HISTORY_MESSAGES` (default 40).

## Deviation from the doc (flagged)

One deliberate behavior-alignment fix, beyond pure cleanup:
`app/main.py::queued_chat` now passes `path=result.path` into the emergency
sync `ChatResponse`. Previously the documented `path: "emergency_override"`
(README §POST /v1/chat, and present in worker-path results via
`schemas.to_dict()`) was silently `null` on the synchronous emergency
response. Caught by the live-model smoke run; one-line fix; full suite green
before and after.

## Live-model smoke

`scripts/smoke_live.py [BASE_URL]` — assumes stack up (`make up`), real
models pulled. Runs general / symptom(+triage) / emergency turns through the
public API, polls jobs, asserts expected pipeline paths. Not part of
pytest; exit code non-zero on mismatch. Last run: PASSED (~70s total,
symptom turn dominant at ~54s).
