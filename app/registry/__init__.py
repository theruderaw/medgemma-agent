"""Neutral addon-contract and registry layer.

Sits between the application runtime and the addons: the runtime imports
ONLY this package, addons implement its Protocol and register instances.
Dependency direction is one-way::

    app  ->  app.registry  <-  app.addons

This package must never import anything from ``app`` itself (enforced by
``scripts/check_architecture.py``).
"""

from .base import (
    DEFAULT_UNAVAILABLE_REPLY,
    Addon,
    SafetyProfile,
    ToolSchema,
)
from .core import (
    addon_names,
    all_addons,
    enabled_addons,
    get,
    get_settings_store,
    register,
    set_settings_store,
    tool_schemas,
)
from .ports import AddonSettingsStore

__all__ = [
    "DEFAULT_UNAVAILABLE_REPLY",
    "Addon",
    "AddonSettingsStore",
    "SafetyProfile",
    "ToolSchema",
    "addon_names",
    "all_addons",
    "enabled_addons",
    "get",
    "get_settings_store",
    "register",
    "set_settings_store",
    "tool_schemas",
]
