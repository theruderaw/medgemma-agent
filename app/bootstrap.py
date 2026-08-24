"""Composition root: the ONLY application module that knows addons exist.

Wires infrastructure into the neutral registry layer and loads every addon
module, once per process, at boot. Because this file is the single seam,
addon changes can never require changes anywhere else in ``app``.
"""

from .addons import load_addons
from .persistence.addon_settings import store as _sql_settings_store
from .registry import set_settings_store

_bootstrapped = False


def bootstrap_addons() -> None:
    """Wire the settings store into the registry, then scan for addons."""
    global _bootstrapped
    if _bootstrapped:
        return
    _bootstrapped = True
    set_settings_store(_sql_settings_store)
    load_addons()
