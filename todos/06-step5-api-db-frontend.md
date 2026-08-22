# Step 5 — Expose Add-on Management (API, DB, Frontend)

**Prerequisite:** Step 4 complete, `pytest` green, multiple features with
distinct safety profiles registered.

**Goal:** let a user see which add-ons exist and turn them on/off, the same
way Claude's connector picker works. This is the only step that touches the
database schema and the frontend.

**Definition of done:** `GET /v1/features` lists all registered features with
enabled state; `POST /v1/features/{name}` toggles one; `feature_registry.enabled_features()`
respects stored state instead of always returning everything; the frontend
has a settings panel rendering toggles that call these endpoints.

## 5.1 — Decide persistence scope first

Check `app/sessions/` and `app/core/db.py` to see whether the app currently
has any concept of a persistent user identity, or whether "session" is the
only durable unit. If there's no user-account concept:

- Default to **session-scoped** feature toggles (stored keyed by
  `session_id`, same table style as wherever session state already lives),
  not global/account-scoped. Don't invent a user-accounts system as a side
  effect of this step — that's out of scope.
- If a global default set is also wanted (e.g. "these 2 features on by
  default for new sessions"), put that in `app/core/config.py` as a setting,
  following the naming convention confirmed in Step 0 §0.6, not in the DB.

## 5.2 — Alembic migration

Add a migration under `alembic/versions/` (copy the structure/style of an
existing migration in that directory — check `alembic/versions/` for the
current pattern before writing a new one). Minimal schema:

```
feature_settings
  session_id   (FK to whatever sessions already use, or nullable if you
                decide to also support a global override row)
  feature_name (str)
  enabled      (bool)
  updated_at   (timestamp)
  PRIMARY KEY (session_id, feature_name)
```

Run `alembic upgrade head` locally and confirm `_run_migrations()` in
`app/main.py` (already runs migrations on startup) picks it up without
error.

## 5.3 — Registry: respect stored state

Update `app/features/registry.py::enabled_features()` to accept an optional
`session_id` and consult the new table (via a small
`app/features/settings.py` module — keep DB access out of `registry.py`
itself, following the existing pattern where `app/core/db.py` owns the
DB session and other modules import from it rather than opening their own
connections):

```python
def enabled_features(session_id: str | None = None) -> list[Feature]:
    all_features = list(_REGISTRY.values())
    if session_id is None:
        return all_features
    disabled = get_disabled_feature_names(session_id)  # from features/settings.py
    return [f for f in all_features if f.name not in disabled]
```

Update every call site from Steps 2–4 (`tool_schemas()` and anywhere else
that iterates `enabled_features()`) to pass `session_id` through — grep for
`enabled_features(` and `tool_schemas(` to find them all in
`app/services/chat.py`.

## 5.4 — API routes

Add to `app/api/schemas.py` (matching existing Pydantic model style):

```python
class FeatureInfo(BaseModel):
    name: str
    description: str
    enabled: bool
    disclaimer_level: str

class FeatureListResponse(BaseModel):
    features: list[FeatureInfo]

class FeatureToggleRequest(BaseModel):
    enabled: bool
```

Add routes in `app/main.py` next to the existing `@app.get("/health")` etc.
(this codebase defines routes directly in `main.py` rather than a separate
router-include pattern — match that, don't introduce
`APIRouter`/`include_router` as a new pattern unless `app/main.py` already
uses it elsewhere; check first):

```python
@app.get("/v1/features")
async def list_features(session_id: str | None = None) -> FeatureListResponse: ...

@app.post("/v1/features/{name}")
async def toggle_feature(name: str, body: FeatureToggleRequest, session_id: str) -> FeatureInfo: ...
```

Return `404` for an unknown feature name (mirror the `HTTPException` pattern
already used in `app/main.py::_prepare_image`).

## 5.5 — Frontend

Look at `frontend/src` structure before adding anything — match the existing
component/state patterns rather than introducing a new one. Add:

- A fetch call to `GET /v1/features` on session load.
- A settings panel (toggle list) that calls `POST /v1/features/{name}` on
  change and optimistically updates local state, rolling back on error.
- Each toggle shows the feature's `description` and, if
  `disclaimer_level == "high"`, a small visual indicator (e.g. a badge) so
  users understand higher-stakes add-ons are being enabled — don't hide this
  distinction in the UI, since Step 4 exists specifically to make it
  meaningful.

## 5.6 — Tests

- API test: toggling a feature off causes a subsequent chat turn's router
  tool list to exclude it (assert via the `routing_decision` audit event's
  recorded tool list, if that's captured — check `app/audit` for what's
  currently logged and extend if the tool list isn't already visible there).
- API test: the clinical-assessment feature (Step 2) and the emergency floor
  are unaffected by any toggle state — confirm a disabled specialist feature
  still doesn't prevent the deterministic emergency check from firing, since
  that check runs before the router is ever consulted and doesn't depend on
  the registry at all.

## What NOT to do in this step

- Do not make the emergency-floor check togglable, ever — it isn't a
  `Feature` and must never be exposed through this system.
- Do not let a disabled `requires_professional_review` feature skip its
  safety profile if it's re-enabled mid-session with a stale cached
  decision — always look up current state at dispatch time in
  `run_chat_turn`, not once at session start.

## Deliverable

New alembic migration, `app/features/settings.py`, updated
`app/features/registry.py`, new schemas in `app/api/schemas.py`, new routes
in `app/main.py`, frontend settings panel, new tests. `pytest` green.
