"""SQL persistence for per-session addon toggles.

Implements the registry layer's ``AddonSettingsStore`` port against the
application database. Owned by the app, not the registry: the neutral
layer stays storage-free and importable without a DB.
"""

import time

from sqlalchemy import delete, select
from sqlmodel import Field, SQLModel

from ..core.db import SessionLocal
from ..registry.ports import AddonSettingsStore


class AddonSettingRow(SQLModel, table=True):
    __tablename__ = "addon_settings"

    session_id: str = Field(
        foreign_key="sessions.session_id", ondelete="CASCADE", primary_key=True
    )
    addon_name: str = Field(primary_key=True)
    enabled: bool
    updated_at: float


class SqlAddonSettingsStore:
    """Session-scoped toggles in the ``addon_settings`` table.

    A missing row means "enabled": only explicit disabled rows are stored,
    so clearing an override and enabling are the same operation.
    """

    async def get_disabled_addon_names(self, session_id: str) -> set[str]:
        async with SessionLocal() as db:
            rows = (
                await db.execute(
                    select(AddonSettingRow.addon_name).where(
                        AddonSettingRow.session_id == session_id,
                        AddonSettingRow.enabled.is_(False),
                    )
                )
            ).scalars().all()
            return set(rows)

    async def set_addon_enabled(
        self, session_id: str, addon_name: str, enabled: bool
    ) -> None:
        async with SessionLocal() as db:
            await db.execute(
                delete(AddonSettingRow).where(
                    AddonSettingRow.session_id == session_id,
                    AddonSettingRow.addon_name == addon_name,
                )
            )
            if not enabled:
                db.add(
                    AddonSettingRow(
                        session_id=session_id,
                        addon_name=addon_name,
                        enabled=False,
                        updated_at=time.time(),
                    )
                )
            await db.commit()


store: AddonSettingsStore = SqlAddonSettingsStore()
