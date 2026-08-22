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
