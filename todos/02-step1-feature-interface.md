# Step 1 — Feature Interface & Registry

**Prerequisite:** Step 0 complete, `pytest` green.

**Goal:** introduce the `Feature` abstraction and a registry that can build
the router's tool list dynamically. **Do not migrate the existing specialist
yet** — that's Step 2. This step only builds the scaffolding and proves it
compiles/imports correctly; the pipeline still behaves exactly as before.

**Definition of done:** a new `app/features/` package exists with the
interface and an empty (or single dummy) registry; `pytest` still passes
unchanged; nothing in `app/services/chat.py` has been rewired yet.

## 1.1 — Create `app/features/__init__.py` and `app/features/base.py`

Follow the existing project conventions: dataclasses for results (see
`app/specialist/parsing.py::SpecialistResult`), Pydantic only for API-facing
schemas (see `app/api/schemas.py`).

```python
# app/features/base.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class SafetyProfile:
    """Per-feature safety configuration. See Step 4 for how this is consumed."""
    requires_professional_review: bool = True
    disclaimer_level: str = "standard"  # "standard" | "high"


@dataclass(frozen=True)
class ToolSchema:
    """OpenAI-style function-calling tool definition for the router."""
    name: str
    description: str
    parameters: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class Feature(Protocol):
    """A pluggable medical capability the router can dispatch to.

    Mirrors the existing SPECIALIST_TOOL / SPECIALIST_SYSTEM_PROMPT /
    parse_specialist_result / specialist_context_for shape already used for
    the clinical-assessment path in app/prompts/specialist.py and
    app/specialist/parsing.py — this Protocol just names that shape so more
    than one feature can implement it.
    """

    name: str                      # matches ToolSchema.name, used for routing
    tool_schema: ToolSchema
    system_prompt: str
    safety_profile: SafetyProfile

    def parse(self, raw_model_output: str) -> Any:
        """Parse raw model output into this feature's structured result type."""
        ...

    def context_for(self, result: Any, **kwargs: Any) -> str | None:
        """Build the system-prompt context string injected before final
        synthesis, mirroring specialist_context_for's signature/shape."""
        ...
```

Keep this minimal. Do not add fields you don't have a concrete use for yet —
every field above is used by name in a later step (`safety_profile` in Step
4, `tool_schema` in 1.2, `context_for` in Step 2).

## 1.2 — Create `app/features/registry.py`

```python
# app/features/registry.py
from __future__ import annotations
from .base import Feature

_REGISTRY: dict[str, Feature] = {}


def register(feature: Feature) -> None:
    if feature.name in _REGISTRY:
        raise ValueError(f"feature '{feature.name}' already registered")
    _REGISTRY[feature.name] = feature


def get(name: str) -> Feature | None:
    return _REGISTRY.get(name)


def enabled_features() -> list[Feature]:
    """Returns all registered features. Step 5 adds a real enabled/disabled
    flag backed by settings/DB — until then, every registered feature is
    considered enabled."""
    return list(_REGISTRY.values())


def tool_schemas() -> list[dict]:
    return [f.tool_schema.as_dict() for f in enabled_features()]
```

Keep registration explicit (an app-level `register()` call at import time in
a central place, e.g. `app/features/__init__.py`) rather than clever
auto-discovery/plugin-scanning — explicit registration is easier to audit for
a safety-sensitive medical app, and matches the rest of this codebase's style
(everything is imported and wired explicitly, e.g. `app/prompts/__init__.py`).

## 1.3 — Do not wire this into `chat.py` yet

Leave `app/services/chat.py` untouched in this step. Confirm the new package
imports cleanly:

```
python -c "import app.features"
pytest
```

Both should succeed with zero behavior change, because nothing calls into
`app/features/` yet.

## 1.4 — Write a throwaway/dummy feature to validate the interface only

Add a tiny test-only feature (e.g. in `tests/` or a `_scratch` module, not in
`app/features/`) that implements `Feature` and confirm
`registry.tool_schemas()` produces valid OpenAI-style tool JSON. Delete this
scratch code before finishing the step — it's a design check, not a
deliverable. The real first feature is Step 2's migrated specialist.

## Deliverable

`app/features/__init__.py`, `app/features/base.py`, `app/features/registry.py`.
No changes anywhere else. `pytest` green.
