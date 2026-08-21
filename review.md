# Streaming (SSE) Overhaul — Review Notes

A guided tour of everything the streaming work changed, why it exists, how
data flows from Ollama to the browser, and what guarantees you can rely on.
File references are `path:section` so you can jump straight to code.

---

## 1. TL;DR

Before this work, `/v1/chat/stream` went silent for long stretches: while
triage, routing, and the MedGemma specialist note were being generated (often
30–120 s combined), the client received **zero bytes**. Worse, a latent bug
meant fully-streamed replies could be stored and delivered as **empty
strings**.

The overhaul makes the stream **never silent** and **fully transparent**:

| Guarantee | How |
|---|---|
| A frame arrives immediately on connect | `start` event emitted before any model work |
| You see every pipeline stage live | audit events forwarded as `pipeline` frames |
| You see MedGemma think | specialist note streams as `specialist_token` frames |
| The token channel never starves | empty `token` heartbeats every 2 s while idle |
| Errors are visible in-stream | named `error` frames with HTTP-style status |

---

## 2. The wire protocol

Every frame is a named Server-Sent Event whose `data:` payload also carries a
`type` field (so both strict `event:`-based parsers and lenient `type`-based
parsers work):

```
event: start
data: {"type": "start", "session_id": null}

event: pipeline
data: {"type": "pipeline", "event": {"module": "image", "event_type": "image_received", ...}}

event: pipeline
data: {"type": "pipeline", "event": {"module": "triage", "event_type": "triage_result", ...}}

event: pipeline
data: {"type": "pipeline", "event": {"module": "router", "event_type": "routing_decision", ...}}

event: specialist_token
data: {"type": "specialist_token", "content": "The image shows "}

event: specialist_token
data: {"type": "specialist_token", "content": "a raised red rash..."}

event: pipeline
data: {"type": "pipeline", "event": {"module": "specialist", "event_type": "specialist_output", ...}}

event: token
data: {"type": "token", "content": "Thanks for "}

event: token
data: {"type": "token", "content": ""}          <-- heartbeat (idle >2s)

event: token
data: {"type": "token", "content": "sharing this."}

event: done
data: {"type": "done", "session_id": "...", "response": "...", "urgency": "urgent", "events": [...]}
```

### Emission order

```
start
  └─ pipeline(image_received)        only if an image was attached
  └─ pipeline(triage_result)         unless triage disabled or safety fired
  └─ pipeline(routing_decision)
       └─ specialist_token*          only on the specialist path
       └─ pipeline(specialist_output)
  └─ token*                          reply chunks + idle heartbeats interleaved
  └─ pipeline(turn_completed)
done
```

On the emergency short-circuit you instead get:
`start → pipeline(safety_override) → token*(fixed response) → done`.

On failure: any prefix, terminated by an `error` frame:

```
event: error
data: {"type": "error", "status": 503, "message": "Model server unreachable: ..."}
```

Status mapping mirrors `POST /v1/chat`: `410` expired session, `502` model
HTTP error, `503` unreachable. Note the stream itself is always HTTP 200 —
errors travel *inside* the stream because headers are already sent.

---

## 3. Backend walkthrough

### 3.1 Token sources — `app/llm/client.py`

Two streaming methods feed the pipeline:

- **`chat_stream()`** — pre-existing; Ollama's OpenAI-compatible
  `/v1/chat/completions` with `stream: true`. Used for the final Qwen
  synthesis.
- **`chat_with_images_stream()`** — new; Ollama's **native** `/api/chat` with
  `stream: true` and an `images: [<base64>]` array attached to the last user
  message. Parses NDJSON lines (`{"message": {"content": "..."}, "done": ...}`)
  and yields content deltas. This is what makes the *vision* call streamable.

Both are async generators, so backpressure is natural: nothing is pulled from
Ollama until the consumer asks for the next delta.

### 3.2 Cleaning tokens mid-flight — `StreamExtractor` (`app/llm/parsing.py`)

Qwen wraps answers in `<response>...</response>` and may emit reasoning first.
`StreamExtractor.feed(delta)` strips the wrapper **live**: it buffers until it
can rule out the opening tag, then releases clean text; when it sees the
closing tag it stops emitting entirely.

Key subtlety (and the source of two bugs — see §5): `feed()` holds anything
shorter than `len("<response>")` = 10 chars in its buffer, and `finish()`
returns whatever remains **only if the closing tag was never seen**. If the
buffer already flushed, `finish()` returns `""`.

### 3.3 Pipeline callbacks — `run_chat_turn()` (`app/services/chat.py`)

The turn function now takes three optional callbacks:

```python
on_event(event: dict)              # every audit event, as it is recorded
on_token(chunk: str)               # final reply deltas
on_specialist_token(chunk: str)    # MedGemma note deltas
```

- `on_event` is invoked inside `record()` — the same events that go to the
  JSONL/Postgres audit trail are handed to the caller in real time. One
  source of truth, two consumers.
- The specialist branch picks its transport by capability:

| Scenario | Call |
|---|---|
| streaming + image | `llm.chat_with_images_stream(...)` |
| streaming, no image | `llm.chat_stream(...)` |
| blocking + image | `llm.chat_with_images(...)` |
| blocking, no image | `llm.chat(...)` |

  In all four cases the **full note** still lands in the
  `specialist_output` audit event — streaming changes transport, not record
  keeping.
- Queued mode (`app/worker.py`) passes none of these callbacks, so Celery
  turns keep the simple blocking path. Streaming is a sync-mode feature.

### 3.4 The pump — `run_chat_turn_stream()` (`app/services/chat.py`)

This is the heart of the overhaul. It runs the full turn on a background
task and converts callbacks into an ordered event stream:

```
runner task                          generator loop
-----------                          --------------
run_chat_turn(...)                   yield {"type":"start", ...}
    │                                     │
    ├─ on_event(e) ───► queue ◄─ wait_for(queue.get(), 2.0s)
    ├─ on_spec_token ──► queue      timeout? yield heartbeat token ""
    ├─ on_token ───────► queue      got item?  yield matching frame
    └─ done ───────────► queue      "result"? break → yield done frame
```

Details worth understanding:

- **One `asyncio.Queue`, tagged tuples.** `(kind, payload)` where kind ∈
  `token | specialist_token | pipeline | result | error`. Ordering is exactly
  production order — no reordering, no loss.
- **Heartbeats via `asyncio.wait_for` timeout.** If nothing arrives within
  `_STREAM_HEARTBEAT_SECONDS` (2.0 s, module-level constant, monkeypatchable
  in tests), the loop yields `{"type": "token", "content": ""}` and waits
  again. This is why the channel flows 100% of the time: either real content
  or a heartbeat, never silence.
- **Errors propagate, not swallow.** The runner catches *everything* into
  `("error", exc)`; the generator re-raises it with
  `raise payload`, so the transport layer (main.py) maps it to an SSE error
  frame. Without this, a mid-turn crash would hang the client forever.
- **Cancellation is clean.** The `finally` block cancels the runner task if
  the client disconnects mid-turn — no orphaned model calls burning GPU.

### 3.5 Transport — `_stream_chat_turn()` (`app/main.py`)

Thin layer: iterates the generator and formats each dict as
`event: <type>\ndata: <json>\n\n`. It owns the exception→frame mapping
(`SessionExpiredError` → 410, `HTTPStatusError` → 502, other `httpx` → 503,
client disconnect → just log and stop). Image validation happens **before**
the stream opens, so bad uploads get a plain `422`, not an error frame.

---

## 4. Frontend walkthrough

### 4.1 Parser — `frontend/src/lib/api.ts`

`streamChat()` reads the body with `ReadableStream` + `TextDecoder`, splits
frames on `\n\n`, extracts the `data:` line, JSON-parses, and dispatches by
`payload.type` to handlers:

| Handler | Fired by |
|---|---|
| `onStart(sessionId)` | `start` |
| `onPipeline(auditEvent)` | `pipeline` |
| `onSpecialistToken(delta)` | `specialist_token` |
| `onToken(delta)` | `token` (including empty heartbeats) |
| `onDone(chatResponse)` | `done` |
| `onError(message, status)` | `error`, non-OK responses, transport failures |

A `202` response still throws `QueuedResponse` so callers fall back to job
polling in queued mode.

### 4.2 State — `frontend/src/hooks/useChat.ts`

Reducer actions added/changed:

- `stream_token` — appends reply text; **ignores empty deltas** (heartbeats
  must not flip the message out of "thinking" state); the **first** non-empty
  delta *replaces* the placeholder instead of appending to it.
- `specialist_token` — appends to `message.specialistNote`, sets
  `specialistStreaming: true`.
- `pipeline_event` — pushes the audit event into `message.events`
  immediately, so the EventTimeline fills in live.
- `turn_success` — finalizes: authoritative text/urgency/events from the
  `done` payload, `specialistStreaming: false`.

### 4.3 Rendering — `MessageBubble.tsx` / `EventTimeline.tsx`

- Assistant bubble shows a green **"Clinical note"** block above the reply
  with an animated writing indicator while `specialistStreaming`.
- Reply text renders with a blinking cursor while `streaming`, then swaps to
  markdown on completion.
- Timeline chips light up as events arrive: `Image received` → `Triage` →
  `Call specialist` / `Image → specialist` → `Specialist note` → `Synthesis`.

---

## 5. Bugs the overhaul surfaced (all fixed)

These are worth knowing because they explain why streaming previously seemed
broken even when tests passed:

1. **Empty streamed replies (the big one).** After streaming, the assembled
   reply was taken from `cleaner.finish()` — which returns `""` whenever
   `feed()` had already flushed its ≥10-char buffer. Any realistic reply was
   stored in the session and sent in `done` as an **empty string**. Old tests
   passed only because their mocked replies were shorter than the buffer
   window. Fix: assemble the reply from emitted chunks plus the finisher tail
   (`"".join(parts)`).
2. **Lost specialist tail.** Same pattern dropped the last buffered chunk of
   the streamed note (e.g. `"note"` out of `"visual findings note"`). Fix:
   emit `finish()`'s remainder as a final `specialist_token`.
3. **Placeholder prefix.** The first real token was appended to
   `"Assistant is thinking…"`, so streamed replies displayed prefixed with
   the placeholder until `done` replaced them. Fix: first token replaces.
4. **Silently unmocked tests.** Two image-pipeline tests weren't stubbing
   every LLM entry point, so they quietly called real Ollama — appearing as
   mysterious 30–120 s "hangs". All model calls are mocked again; the suite
   runs offline in ~2.5 s.

---

## 6. Guarantees & edge cases cheat-sheet

| Situation | Behavior |
|---|---|
| Client connects | `start` frame immediately, before any model I/O |
| Triage/router running (seconds) | `pipeline` frames when each finishes; heartbeats between |
| MedGemma writing a long note | `specialist_token` frames as it writes |
| Nothing ready for >2 s | empty `token` heartbeat |
| Client disconnects mid-turn | runner task cancelled; nothing leaks |
| Model server dies mid-turn | single `error` frame (502/503), stream ends |
| Expired session id | `error` frame (410); client clears stored session |
| Invalid image | plain `422` — stream never opens |
| Queued mode (`PROCESSING_MODE=queued`) | `202` + `job_id`; polling fallback, no SSE |
| Emergency short-circuit | `pipeline(safety_override)` then fixed reply tokens |

---

## 7. How to verify

Automated (offline, ~2.5 s total):

```sh
.venv/bin/python -m pytest tests/test_streaming.py -q   # streaming contract
.venv/bin/python -m pytest tests/ -q                    # everything (140 tests)
cd frontend && npx tsc --noEmit                         # frontend types
```

`tests/test_streaming.py` pins the contract:

- `test_stream_event_ordering_covers_every_stage` — exact frame sequence for
  an image turn through the specialist path, including token joins.
- `test_stream_general_path_still_streams_reply` — direct-reply path.
- `test_stream_emits_heartbeats_while_models_run` — heartbeats appear during
  a slow stage (timeout patched to 10 ms).
- `test_sse_framing_uses_named_events` — `event:` names present and ordered.
- `test_sse_error_frame_on_model_failure` — in-stream 503 mapping.
- `test_stream_rejects_invalid_image_before_stream_opens` — 422 gate.
- `test_worker_path_does_not_stream_specialist` — queued mode unchanged.

Manual smoke test (requires Ollama up):

```sh
curl -N -X POST http://localhost:8000/v1/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message": "I have a rash on my arm, should I see a doctor?"}'
```

You should see `start`, then `pipeline` frames, then `specialist_token`
frames, then `token` frames, then `done` — with heartbeats filling any gap
longer than 2 seconds.
