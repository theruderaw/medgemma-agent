"""Storage port for per-session addon toggles.

The registry layer defines only this interface; a concrete implementation
(SQL, memory, remote API) is supplied by the host application at boot via
``registry.set_settings_store``. Until one is wired, every addon counts as
enabled everywhere.
"""

from __future__ import annotations

from typing import Protocol


class AddonSettingsStore(Protocol):
    async def get_disabled_addon_names(self, session_id: str) -> set[str]:
        """Names of addons explicitly disabled for this session."""
        ...

    async def set_addon_enabled(
        self, session_id: str, addon_name: str, enabled: bool
    ) -> None:
        """Persist one toggle for a session (insert, update, or clear)."""
        ...
