"""In-memory addon registry: name -> instance, plus the settings-store slot.

The registry never imports application code. Addons register themselves
through :func:`register`; the runtime looks addons up by name; per-session
enable/disable state is delegated to whatever ``AddonSettingsStore`` the
host application wired at boot (all-enabled until one is).
"""

from __future__ import annotations

from .base import Addon
from .ports import AddonSettingsStore

_REGISTRY: dict[str, Addon] = {}
_settings_store: AddonSettingsStore | None = None


def set_settings_store(store: AddonSettingsStore) -> None:
    """Wire the persistence backend for session toggles (called at boot)."""
    global _settings_store
    _settings_store = store


def get_settings_store() -> AddonSettingsStore:
    """The wired store; raises before boot wiring instead of silently
    losing toggles."""
    if _settings_store is None:
        raise RuntimeError(
            "addon settings store not wired: call registry.set_settings_store()"
            " during application bootstrap"
        )
    return _settings_store


def register(addon: Addon) -> None:
    if addon.name in _REGISTRY:
        raise ValueError(f"addon '{addon.name}' already registered")
    _REGISTRY[addon.name] = addon


def get(name: str) -> Addon | None:
    return _REGISTRY.get(name)


def all_addons() -> list[Addon]:
    """Every registered addon, regardless of session-level toggle state."""
    return list(_REGISTRY.values())


async def enabled_addons(session_id: str | None = None) -> list[Addon]:
    """All registered addons, minus those explicitly disabled for the
    session. ``session_id=None`` (no session context) returns everything."""
    addons = all_addons()
    if session_id is None or _settings_store is None:
        return addons
    disabled = await _settings_store.get_disabled_addon_names(session_id)
    return [a for a in addons if a.name not in disabled]


def addon_names(addons: list[Addon] | None = None) -> list[str]:
    """Names of the given addons (all registered ones by default)."""
    return [a.name for a in (addons if addons is not None else _REGISTRY.values())]


async def tool_schemas(session_id: str | None = None) -> list[dict]:
    enabled = await enabled_addons(session_id)
    return [a.tool_schema.as_dict() for a in enabled]
