from __future__ import annotations

from .base import Feature
from .settings import get_disabled_feature_names

_REGISTRY: dict[str, Feature] = {}


def register(feature: Feature) -> None:
    if feature.name in _REGISTRY:
        raise ValueError(f"feature '{feature.name}' already registered")
    _REGISTRY[feature.name] = feature


def get(name: str) -> Feature | None:
    return _REGISTRY.get(name)


def all_features() -> list[Feature]:
    """Every registered feature, regardless of session-level toggle state."""
    return list(_REGISTRY.values())


async def enabled_features(session_id: str | None = None) -> list[Feature]:
    """All registered features, minus those explicitly disabled for the
    session. ``session_id=None`` (no session context) returns everything."""
    all_features = list(_REGISTRY.values())
    if session_id is None:
        return all_features
    disabled = await get_disabled_feature_names(session_id)
    return [f for f in all_features if f.name not in disabled]


def feature_names(features: list[Feature] | None = None) -> list[str]:
    """Names of the given features (all registered ones by default)."""
    return [f.name for f in (features if features is not None else _REGISTRY.values())]


async def tool_schemas(session_id: str | None = None) -> list[dict]:
    enabled = await enabled_features(session_id)
    return [f.tool_schema.as_dict() for f in enabled]
