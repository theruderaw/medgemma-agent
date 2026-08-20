# MedGemma Agent — Milestone 6.3

Frontend: a React + Vite chat UI for the existing FastAPI backend, plus a true
token-streaming path (`POST /chat/stream`, SSE) so replies render live instead
of arriving all at once after inference finishes.

## What changed

### New: `frontend/` (React 19 + Vite + Tailwind v4)

- **`src/types.ts`** — shared types: `ChatResponse`, `TurnEvent`, `Urgency`
  (`emergency | medical | general | null`), `PipelineEvent`, session payloads.
- **`src/lib/api.ts`** — typed API client:
  - **`streamChat()`** — `fetch` + a small SSE parser that splits `data:`
    frames and dispatches `token` / `done` / `error` events (respects the
    event name from each frame, falls back to `message`). Throws a custom
    **`QueuedResponse`** when the backend answers `202` (queued mode), so the
    caller can transparently switch to polling.
  - `waitForJob()` / `pollJob()` — queued-mode fallback that polls
    `GET /jobs/{job_id}` until `success`, then resolves the `ChatResponse`.
  - `health()` and the session-reset call.
- **`src/hooks/useChat.ts`** — single `useReducer` driving message state
  (`send_start` / `stream_token` / `turn_success` / `turn_error` /
  `acknowledge` / `new_chat`). `send()` calls `streamChat`, appending
  `token` chunks to the assistant message, and surfaces the `urgency` from
  `done` as a modal/banner. A failed turn removes the placeholder thinking
  bubble and restores the input.
- **`src/hooks/useHealth.ts`** — polls `GET /health` to show model/server
  status in the header.
- **Components** (`src/components/`):
  - `Header` — session controls + health indicator.
  - `ChatInput` — message box + send; disabled while a turn streams.
  - `MessageList` / `MessageBubble` — show **raw text while streaming**
    (`whitespace-pre-wrap`), then re-render as markdown when the stream
    completes.
  - `Markdown` — `react-markdown` + `remark-gfm` with Tailwind Typography
    (`prose prose-invert prose-sm`); links open in a new tab.
  - `EventTimeline` — vertical, connected step panels derived from the turn's
    pipeline events (`Triage` → `Call specialist` → `Specialist note` →
    `Synthesis`); click a step to expand its payload.
  - `UrgencyBanner` — `URGENCY: URGENT / MEDICAL / GENERAL` line
    (red/amber/green) above non-emergency replies.
  - `UrgencyModal` — full-screen emergency overlay that dismisses only when the
    ack input matches `/^accepted[a-z]{4}$/i` (e.g. `acceptedxyzw`); the
    backdrop is not click-dismissable and the emergency reply stays visible
    behind the modal.
- **Styling** — Tailwind v4 through the `@tailwindcss/vite` plugin:
  `@import 'tailwindcss'`, `@plugin '@tailwindcss/typography'`, a `@theme`
  blink animation for the streaming caret, and `@layer base` rules for
  scrollbars / `:focus-visible` / body colors. All hand-written CSS removed.
- **`vite.config.ts`** — dev proxy for `/chat`, `/chat/stream`, `/jobs`,
  `/sessions`, `/health` → `http://localhost:8000` (configurable via
  `VITE_BACKEND_URL`), so no CORS setup is needed.

### Backend: real token streaming

- **`app/llm/client.py` — `LLMClient.chat_stream()`** — async generator over
  Ollama's OpenAI-compatible `/v1/chat/completions` with `stream: true` and
  `enable_thinking: false`; yields `delta.content` chunks as they arrive.
- **`app/llm/parsing.py` — `StreamExtractor`** — strips the Qwen3
  `<response>...</response>` wrapper live from a stream. With
  `enable_thinking: false` the wrapper (when present) leads the content, so the
  extractor holds back only the first few characters to detect a leading tag,
  then streams everything eagerly and truncates at `</response>`. This gives
  clients genuine incremental tokens (previously it buffered the whole reply
  for wrapper-less responses and flushed it in one burst at the end).
- **`app/services/chat.py`** — `run_chat_turn(..., on_token=None)` accepts a
  token callback: the specialist path pipes synthesis tokens through it, the
  general/direct path emits `extract_answer(routing.content)` in small chunks.
  **`run_chat_turn_stream()`** wraps that as an async generator that yields
  `{"type": "token"}` / `{"type": "done"}` / `{"type": "error"}` events.
- **`app/main.py`** — **`POST /chat/stream`** returns `text/event-stream`:
  `token` events as the reply streams, then a `done` event carrying the full
  `ChatResponse` (session id, response, urgency, pipeline events), or an
  `error` event. Error mapping matches `POST /chat` (`410` expired session,
  `502`/`503` model-server failures). In queued mode it returns the same `202`
  + `job_id` as `/chat` and the frontend falls back to polling.

## Tests

- No new automated tests were added for the streaming endpoint this milestone;
  it was verified end-to-end against a live Ollama server (see Verification).
  The existing suite is unchanged and still green.

## Configuration

No new env vars. The frontend is configured at the Vite layer:

```text
VITE_BACKEND_URL=http://localhost:8000   # dev-proxy target (default)
```

## Verification

- `npm run build` in `frontend/` passes (TypeScript + Vite production build).
- `curl` against `POST /chat/stream` returned incremental `data:` `token`
  events for a wrapped (specialist) response and an immediate `done` for an
  emergency safety-floor short-circuit.
- Live timing vs. live Ollama (local box, 4B models):
  - General reply ("What is the capital of France?"): first token ~9–22 s
    (dominated by the pre-stream pipeline: triage + routing), stream phase
    ~17–22 ms for the already-generated reply.
  - Specialist reply (headache/dizziness): first token ~68–141 s, then a real
    streaming phase of ~30 s / 228 token events / ~2,800 chars (~16 chars/s).
- Browser check (Playwright) confirmed: markdown rendering, event-timeline
  expansion, and the urgency modal/ack flow.

## Notes / trade-offs

- **TTFT is pipeline-bound, not stream-bound.** The time to first token is
  dominated by triage → routing → (specialist) → synthesis running before any
  content exists; `/chat/stream` only removes the wait after the reply starts.
  Shortening TTFT would mean streaming intermediate steps (thinking / events)
  rather than only the final reply.
- **The typewriter is gone.** It was replaced by real backend streaming, so the
  incremental effect is honest rather than simulated.
- **Markdown renders only after the stream completes** — mid-stream text is
  shown raw to avoid layout/reflow churn on partial markdown.
- **Queued mode is unchanged** — `/chat/stream` degrades to the `202` + polling
  flow so the UI works in both modes.
- **`StreamExtractor` relies on `enable_thinking: false`** so the
  `<response>` tag leads the content; a response that embeds the tag later
  would pass it through (pre-existing limitation of `extract_answer`).

## Out of scope (this milestone)

- Streaming the intermediate pipeline events (thinking, tool calls) to the
  frontend before the final reply — only the final reply is streamed today.
- Automated tests for `/chat/stream`.
- Image upload (models are text-only).