# fix-todos.md — Bug Fix Checklist

Findings from a manual code review of `app/` (backend) and `frontend/src/`
(frontend). Ordered by priority. Check items off as they land; note any
deviation the way `todos/PROGRESS.md` does.

---

## P0 — Safety-critical

- [x] **Emergency acknowledgment gate can be dismissed with zero friction**
  `frontend/src/components/chat/EmergencyGate.tsx` passes
  `onClose={onAcknowledge}` into the shared `Modal`, which wires `onClose` to
  both Escape-key and backdrop-click. A stray click on the overlay or an
  Escape tap dismisses the emergency warning instantly — no typed
  acknowledgment required. This defeats the one deliberate-friction safety
  mechanism in the UI.
  - Fix: add a `dismissible` prop to `Modal` (default `true`); have
    `EmergencyGate` pass `dismissible={false}` so only the typed-pattern
    match (`ACK_PATTERN`) can close it.
  - Files: `frontend/src/components/ui/Modal.tsx`,
    `frontend/src/components/chat/EmergencyGate.tsx`

  **Landed:** `dismissible?: boolean` (default true) on `Modal`; Escape and
  backdrop-click handlers are inert when false. `EmergencyGate` passes
  `dismissible={false}` and no longer passes `onClose` (made optional —
  deviation: there is no close path but the typed ack, so keeping a dead
  handler invited misuse).

- [x] **Output guardrail is effectively off for the default (non-triage) flow**
  `run_output_guard` skips the guard-model call entirely whenever
  `urgency is None`. Since triage is opt-in and off by default, most turns
  never get judged for `missing_disclaimer` or `unsafe_wording` (no
  deterministic backstop exists for either), and `diagnostic_claim` only has
  narrow keyword coverage via `_CERTAINTY_RE`. This contradicts the
  documented "always on" behavior (README, and the comment directly above
  the call site in `chat.py`).
  - Fix: decide the intended behavior explicitly — either (a) run the guard
    model regardless of triage opt-in (drop the `urgency is None` branch of
    the skip condition, keep the `< guard_min_chars` skip), or (b) if the
    short-circuit is intentional for cost/latency reasons, update the
    README and the misleading in-code comment to say so, and consider
    widening the deterministic regex coverage to compensate.
  - Files: `app/safety/output.py` (`run_output_guard`), `app/services/chat.py`
    (call site + comment), `README.md`

  **Landed:** option (a) — skip is now length-only (`< GUARD_MIN_CHARS`);
  README table row + Output-guardrails section updated to match. Companion
  change: dropped the `urgency is not None` gate on the `missing_disclaimer`
  verdict — otherwise non-triage turns would be judged but that flag could
  never fire, making the run pointless for exactly the flow this item
  re-enables. Verified manually (mocked guard): long untriaged reply →
  judged + disclaimer appended; short reply → still skipped.

---

## P1 — Correctness bugs

- [x] **`StreamExtractor.feed()` re-buffers tokens for the rest of the stream**
  The `len(self.buf) < len(self.OPEN_TAG)` gate re-triggers on every call
  because `self.buf` resets to `""` after each flush, not just at stream
  start. Small deltas get batched into ≥10-char chunks instead of streaming
  immediately, contradicting the class's own docstring and causing visibly
  chunky/delayed live token output.
  - Fix: track "still checking for the open tag" as a one-time boolean state
    (e.g. `self._checked_open: bool`), only apply the length-gate before
    that flag is set, and stream every delta through untouched afterward.
  - File: `app/llm/parsing.py` (`StreamExtractor.feed`)

- [x] **`StreamExtractor` doesn't handle `</response>` split across two deltas**
  `feed()` searches for `CLOSE_TAG` only within the current call's flushed
  text, not across buffered state. If the model server splits the tag
  across chunks (e.g. `...</respo` then `nse>...`), it's never detected —
  `done` never becomes `True` and both fragments leak into the visible
  stream. The open tag has explicit partial-match protection; the close tag
  has none.
  - Fix: hold back a small tail (`len(CLOSE_TAG) - 1` chars) of each flush
    instead of emitting everything immediately, so a split closing tag can
    still be detected on the next `feed()` call. Flush the held-back tail
    in `finish()` if the stream ends without a close tag appearing.
  - File: `app/llm/parsing.py` (`StreamExtractor.feed`, `.finish`)

  **Landed (both):** one-time `_checked_open` probe + a rolling
  `_tail` holdback of `len(CLOSE_TAG) - 1` chars, flushed verbatim by
  `finish()`. Deviation found while verifying against the real streamed
  chunks in `test_chat_flow`: the old `finish()` returned `buf.strip()`;
  stripping the new tail corrupts wording whenever the holdback starts
  mid-sentence ("monitor your symptoms" → "monitor yoursymptoms"), so
  `finish()` now returns the tail untouched. Verified manually with the
  fake server's 8-char chunking: single-char steady-state flow, split close
  tag (wrapped and unwrapped bodies), post-close suppression, tail flush.

---

## P2 — Production hardening

- [x] **No error boundary in the frontend render tree**
  `main.tsx` renders `<App />` with nothing catching render-time exceptions.
  Any unhandled error white-screens the whole app, including the emergency
  gate and composer, with no recovery path.
  - Fix: add a top-level `ErrorBoundary` around `<App />` with a
    "something went wrong — refresh to continue" fallback. Consider a
    second, narrower boundary around `MessageList` so one malformed message
    can't take down the composer.
  - Files: `frontend/src/main.tsx`, new `ErrorBoundary` component

  **Landed:** generic `ErrorBoundary` (console.error + reset affordance)
  around `<App />`; narrower boundary around `MessageList` inside ChatView
  keeps the composer usable if rendering history throws.

- [x] **`resetSession` silently swallows failures**
  `api.ts::resetSession` doesn't check `res.ok`, and its only caller wraps
  it in `try { } catch { /* best-effort reset */ }` — a failed DELETE (5xx,
  network blip) is invisible with no logging, so server-side session leaks
  go undetected in production.
  - Fix: check `res.ok` and at least `console.warn`/report to telemetry on
    failure; keep the best-effort *behavior* (don't block `newChat`), just
    stop discarding the signal.
  - File: `frontend/src/lib/api.ts` (`resetSession`)

- [x] **No production API base URL configuration**
  Every request in `api.ts` uses relative paths. This only works when the
  built frontend is served same-origin with the API (or behind a proxy that
  forwards those paths) — there's no build-time equivalent of the dev-only
  Vite proxy (`VITE_BACKEND_URL`) for a production build where frontend and
  backend might live on different origins.
  - Fix: add a `VITE_API_BASE_URL` build-time env var, defaulting to `''`
    (same-origin, matching current behavior) so nothing changes today but
    the seam exists for a split deployment.
  - Files: `frontend/src/lib/api.ts`, `frontend/vite.config.ts` (docs/env
    wiring)

  **Landed:** every request (incl. the SSE EventSource) goes through
  `apiUrl()`, prefixed by `import.meta.env.VITE_API_BASE_URL ?? ''`.
  Typed in `vite-env.d.ts`; README build/deploy section documents it.
  Deviation: `vite.config.ts` itself needed no change — Vite exposes
  `VITE_*` vars at build time automatically.

- [x] **Duplicated image validation constants between frontend and backend**
  `Composer.tsx` hardcodes `MAX_BYTES = 5 * 1024 * 1024` and the MIME
  allowlist, duplicating `IMAGE_MAX_BYTES` / `IMAGE_ALLOWED_MIME` from the
  backend `.env`. If the backend limits are ever tuned, the client-side
  pre-check silently drifts out of sync (backend still re-validates
  correctly, but users get misleading client-side errors).
  - Fix: surface these limits from `GET /v1/features` (or a small
    `GET /v1/config` endpoint) instead of hardcoding them twice.
  - Files: `frontend/src/components/chat/Composer.tsx`, `app/main.py`
    (new/extended endpoint)

  **Landed:** new `GET /v1/config` serving `image_max_bytes` +
  `image_allowed_mime` straight from settings (`AppConfigResponse`).
  Composer fetches it on mount and derives its pre-checks, file-input
  accept list, and attach-button tooltip from the response. Deviation:
  chose a dedicated `/v1/config` over extending `/v1/features` (limits are
  global policy, not feature state). Backend defaults remain as initial
  state only until the fetch resolves/fails — noted in-file as the one
  residual duplication, active solely when the config request fails.

---

## Notes

- Items above were found via manual review, not the (currently red)
  integration test suite — no test-infra changes are included here.
- Recommend adding a regression test per P0/P1 item once the fix lands, so
  each stays fixed (e.g. an EmergencyGate interaction test asserting
  Escape/backdrop-click do *not* dismiss; a `StreamExtractor` unit test
  feeding single-character deltas and a split closing tag).
- Verification done manually for now (no regression tests written yet):
  frontend `tsc -b && vite build` clean; mocked-guard script for P0-2;
  scripted checks for P1 parsing edge cases; `TestClient` hit on
  `/v1/config`; full suite run — 54 passed, 2 failed
  (`test_triage_endpoint.py::test_model_classification_for_plain_text`,
  `::test_image_stored_and_audited_but_never_classified`) — both fail
  identically on a clean checkout (pre-existing, unrelated).
