# MedGemma Agent — Milestone 3

Bring in MedGemma with dumb routing. Two-model architecture validated
end-to-end: Qwen3-4B orchestrates, MedGemma 4B specialists, Qwen synthesizes.

## What changed

### New module: `app/router.py`

`should_route_to_specialist(message)` — a naive keyword router. Substring match
against the lowercased message for: `pain, hurts, symptom, fever, headache,
bleeding, swelling, nausea, cough`. Over-matching and under-matching are
expected at this stage.

### Changed: `app/llm.py`

`LLMClient.chat` gained a `model` parameter (`model or settings.model_name`),
so a single client can call either Qwen or MedGemma through the same
OpenAI-compatible endpoint.

### Changed: `app/main.py`

`POST /chat` now routes each turn:

1. If the router matches, call the specialist with
   `[SPECIALIST_SYSTEM_PROMPT, user message]` on `SPECIALIST_MODEL_NAME`.
2. Build Qwen's messages as `[system, <specialist context>, ...history]` — the
   specialist note is injected as an extra system message via
   `SPECIALIST_CONTEXT` (`"A clinical specialist model produced the following
   note: ... Respond to the user using this information in clear, plain
   language."`).
3. Call Qwen (`MODEL_NAME`) for the final synthesis.

General (non-matching) turns skip the specialist entirely and Qwen answers
directly with the conversation history. Error handling is shared: any model
call failure maps to `502`/`503`.

### Changed: `app/prompts.py`

Added `SPECIALIST_SYSTEM_PROMPT` (asks for a concise clinical note with
observations, red flags, urgency — no definitive diagnosis) and
`SPECIALIST_CONTEXT` (how the note is framed for Qwen).

### Changed: `app/config.py`

New setting `SPECIALIST_MODEL_NAME` (default `medgemma:4b`).

## Logic notes

- Routing uses only the current user message, not the full history.
- The specialist sees only the current turn — the conversation context is
  carried by Qwen.
- The specialist note is non-structured free text at this stage; structured
  output (urgency/red-flags schema) arrives in Milestone 4.
- The `medgemma:4b` default is a config value; point it at the tag your Ollama
  install uses.

## Configuration

New env var (see `.env.example`): `SPECIALIST_MODEL_NAME`.

## Tests

- `tests/test_router.py` (new) — keyword matching, general-message passthrough,
  clinical message makes exactly two model calls (specialist then synthesis)
  with the specialist context injected, routing resets per turn, specialist
  failure maps to `503`.
- `tests/test_chat.py` — fakes updated for the `model` kwarg; accumulation test
  uses non-clinical messages so it exercises the direct path.

## Still missing

- Real triage
- Structured specialist output
- Emergency override
- Context-aware routing (function calling)
- Prescription reading
- Context summarization
- Multi-user concurrency (one user at a time)