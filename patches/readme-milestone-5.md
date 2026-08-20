# MedGemma Agent — Milestone 5

Contextual routing via function calling. Replaces the naive keyword router with
a Qwen-driven decision: Qwen is given a `call_medical_specialist(reason)`
function and decides — based on the actual conversation — whether a clinical
specialist (MedGemma) note is needed.

## What changed

### New module: `app/routes/function_calling.py`

Replaces `app/routes/keyword.py` (deleted).

- **`RouteCategory`** — `general`, `symptom_related`, `emergency`.
- **`RouteDecision`** — a category plus the optional `reason` from the tool call.
- **`parse_tool_calls(tool_calls) -> RouteDecision`** — interprets the model's
  `tool_calls` array. A `call_medical_specialist` call becomes
  `SYMPTOM_RELATED` (with the parsed `reason`); anything else is `GENERAL`.
- **Critical invariant:** `parse_tool_calls` can never return `EMERGENCY`. The
  `emergency` category is owned exclusively by the independent hardcoded safety
  check in `app/safety.py`, which runs first and short-circuits before any model
  call. The classifier cannot route around the emergency layer.

### New module: `app/prompts/routing.py`

- **`SPECIALIST_TOOL`** — OpenAI-compatible function schema for
  `call_medical_specialist(reason: str)`.
- **`ROUTING_SYSTEM_PROMPT`** — instructs Qwen to call the tool only for real
  health symptoms/concerns, reply directly otherwise, and never attempt to
  handle emergencies itself.

### Changed: `app/llm.py`

- New **`LLMClient.chat_with_tools(messages, tools, ...) -> ChatResult`** —
  OpenAI-compatible `/v1/chat/completions` with `tools` + `tool_choice: auto`.
  Returns `ChatResult(content, tool_calls)` so the caller can inspect whether a
  tool was requested.
- `ChatResult` dataclass added.
- **`extract_answer(content)`** — Qwen3 occasionally wraps its real reply in a
  reasoning preamble and `<response>...</response>` tags. This helper returns
  the inner answer when the tags are present, otherwise the trimmed content.
  Applied to the direct general-path reply and defensively to the synthesized
  reply in `app/services/chat.py`.
- `chat()` and `chat_with_tools()` send `enable_thinking: False`: with thinking
  enabled the reply text is unreliable (preamble, truncated or missing
  answers); with it disabled the `<response>` tags are consistently present and
  `extract_answer` cleanly recovers the final reply.

### Changed: `app/services/chat.py`

Per-turn flow:

1. Append user message.
2. **Safety floor** (when `TRIAGE_ENABLED`): `detect_emergency` short-circuits
   — unchanged, still first and independent.
3. **Triage** (when `TRIAGE_ENABLED`): soft calibration signal — unchanged.
4. **Routing** (replaces keyword match): Qwen routing call with
   `SPECIALIST_TOOL`.
   - Tool called → MedGemma note from the `reason` → injected into Qwen's
     synthesis context.
   - No tool call → Qwen's routing reply is the final answer (one model call
     for general turns).

### Changed: `tests/`

- `tests/test_router.py` — rewritten for function-calling: tool-call parsing
  (present/absent/unknown/malformed), the invariant that `EMERGENCY` is never
  produced by the router, routing to specialist + synthesis on a tool call, the
  direct general path making no `llm.chat` call, reset allowing a clinical
  session to return to general, specialist failure → `503`.
- `tests/test_chat.py` — mocks now target `llm.chat_with_tools`; general turns
  assert the routing reply is returned directly; `extract_answer` unit tests
  (tagged response extraction, plain-content passthrough).
- `tests/test_triage.py` — triage urgency now reaches the routing context; the
  emergency short-circuit test also forbids `chat_with_tools`.

## Routing categories

```text
general           → Qwen replies directly (no specialist)
symptom_related   → Qwen calls call_medical_specialist → MedGemma → synthesis
emergency         → ONLY the hardcoded safety check (never the router)
```

## Benefits

- Fewer missed clinical turns (context, not keywords)
- Fewer unnecessary MedGemma calls
- Faster general conversation (single model call)
- Clear separation between orchestration and specialist reasoning

## Still missing

- Prescription reading
- Audit logging
- Clinically reviewed red-flag list (placeholder)
- Context summarization
- Multi-hop tool chains / persistent tool context
- Multi-user concurrency (one user at a time)