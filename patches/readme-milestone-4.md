# MedGemma Agent — Milestone 4

Real triage output + hardcoded escalation. Adds a deterministic safety floor
and a tiny triage classifier on top of the two-model routing from Milestone 3.

## What changed

### New module: `app/triage.py`

- **`RED_FLAG_RULES`** — deterministic regex rules over the raw user text:
  chest pain, breathing difficulty, stroke signs, suicidal ideation, severe
  bleeding, anaphylaxis signs, seizure, unconsciousness.
- **`detect_emergency(text) -> str | None`** — returns the matched category or
  `None`. This is the safety floor; it never depends on any model output,
  confidence, or routing decision.
- **`EMERGENCY_RESPONSE`** — fixed short-circuit reply asking the user to call
  emergency services.
- **`parse_triage_urgency(raw) -> str`** — tolerantly parses the tiny triage
  model's JSON (strips code fences/prose, validates the value against
  `emergency | medical | general`).

### Changed: `app/llm.py`

New `LLMClient.triage(message)` method that calls Ollama's **native `/api/chat`**
endpoint with a JSON-schema `format` parameter, so the tiny model is
*constrained* to emit exactly:

```json
{"urgency": "emergency" | "medical" | "general"}
```

Schema lives in `app/prompts.py` (`TRIAGE_FORMAT`), prompt in `TRIAGE_PROMPT`.
Uses `temperature=0.0`.

### Changed: `app/prompts.py`

- `TRIAGE_PROMPT` — short classifier instruction for the tiny model.
- `TRIAGE_FORMAT` — Ollama JSON-schema constraint (enum of three urgencies).
- `TRIAGE_CONTEXT` — how the triage verdict is framed for Qwen synthesis.
- Kept `SPECIALIST_SYSTEM_PROMPT` / `SPECIALIST_CONTEXT` for MedGemma.

### Changed: `app/main.py`

`POST /chat` flow per turn:

1. Append user message.
2. **Safety floor** (when `TRIAGE_ENABLED`): run `detect_emergency`. On a
   match, append the `EMERGENCY_RESPONSE` to history, save, and return
   immediately — no model is called.
3. **Triage** (when `TRIAGE_ENABLED`): call `llm.triage`, parse the urgency,
   and inject it into Qwen's context as a system message. This is a soft
   calibration signal, not a short-circuit.
4. **Routing** (unchanged from Milestone 3): keyword match → MedGemma note
   injected as context.
5. Qwen synthesizes the final response with system + triage context +
   specialist context + history.

With `TRIAGE_ENABLED=false`, the app behaves as Milestone 3 (no escalation, no
triage call).

### Changed: `app/config.py`

New settings: `TRIAGE_MODEL_NAME` (default `qwen3:0.6b`), `TRIAGE_ENABLED`
(default `true`).

## Critical principle

The emergency decision is **deterministic code only**:

- Not Qwen, not MedGemma, not the triage model
- Not confidence scores
- Not routing decisions
- Not final wording

The triage model's `"emergency"` verdict is a signal Qwen can weigh, but only
`detect_emergency` can short-circuit.

## Configuration

New env vars (see `.env.example`): `TRIAGE_MODEL_NAME`, `TRIAGE_ENABLED`.

## Tests

- `tests/test_triage.py` (new) — red-flag matching per category, benign-text
  passthrough, case insensitivity, triage-urgency parsing (valid/tolerant/
  invalid), emergency short-circuit with zero model calls, triage urgency
  reaching the synthesis context, `TRIAGE_ENABLED=false` skipping both
  escalation and triage, triage failure → `503`.
- `tests/test_chat.py` / `tests/test_router.py` — added autouse `llm.triage`
  mock; synthesis message layout updated for the extra triage context message.

## Still missing

- Context-aware routing (function calling)
- Prescription reading
- Audit logging
- Clinically reviewed red-flag list (placeholder)
- Context summarization
- Multi-user concurrency (one user at a time)