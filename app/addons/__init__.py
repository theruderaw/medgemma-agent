"""Concrete addons. This package contains ONLY feature implementations.

Nothing in the application imports this package except the composition
root (``app.bootstrap``), which calls :func:`load_addons` once at boot.
Adding a feature is a drop-in: any ``*.py`` module here that exposes a
module-level ``addon`` instance (implementing ``app.registry.Addon``) is
imported and registered automatically; removing the file removes the
feature. No registration lists exist anywhere.

Loading is defensive by design: a broken module (syntax error, corrupt
dataset, bad import) or one without an ``addon`` instance is logged and
skipped so it can never prevent the application from booting.
"""

import importlib
import pkgutil

import structlog

from ..registry import register

logger = structlog.get_logger(__name__)

_loaded = False


def load_addons() -> None:
    """Scan this package once and register every module's ``addon``."""
    global _loaded
    if _loaded:
        return
    _loaded = True
    for info in pkgutil.iter_modules(__path__):
        if info.name.startswith("_"):
            continue
        try:
            module = importlib.import_module(f"{__package__}.{info.name}")
        except Exception:
            logger.exception("addon.load_failed", module=info.name)
            continue
        instance = getattr(module, "addon", None)
        if instance is None:
            logger.warning(
                "addon.no_instance",
                module=info.name,
                hint="expose a module-level 'addon' to register it",
            )
            continue
        try:
            register(instance)
        except Exception:
            logger.exception("addon.registration_failed", module=info.name)
