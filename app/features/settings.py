"""Per-session feature toggle persistence.

Owns all DB access for ``feature_settings`` so that ``registry.py`` stays
storage-free (mirrors how other modules consume ``core.db.SessionLocal``
rather than opening their own connections).

Toggles are session-scoped by design (Step 5 §5.1): there is no user-account
concept in this app, so a missing row means "enabled" — only explicit
disabled rows are stored.
"""

import time

from sqlalchemy import delete, select

from ..core.db import SessionLocal
from ..core.models import FeatureSettingRow


async def get_disabled_feature_names(session_id: str) -> set[str]:
    """Return the names of features explicitly disabled for this session."""
    async with SessionLocal() as db:
        rows = (
            await db.execute(
                select(FeatureSettingRow.feature_name).where(
                    FeatureSettingRow.session_id == session_id,
                    FeatureSettingRow.enabled.is_(False),
                )
            )
        ).scalars().all()
        return set(rows)


async def set_feature_enabled(session_id: str, feature_name: str, enabled: bool) -> None:
    """Persist one toggle row for a session (insert or update)."""
    async with SessionLocal() as db:
        await db.execute(
            delete(FeatureSettingRow).where(
                FeatureSettingRow.session_id == session_id,
                FeatureSettingRow.feature_name == feature_name,
            )
        )
        if not enabled:
            # Absence of a row means enabled; only disabled state is stored,
            # keeping "reset to default" equivalent to deleting the override.
            db.add(
                FeatureSettingRow(
                    session_id=session_id,
                    feature_name=feature_name,
                    enabled=False,
                    updated_at=time.time(),
                )
            )
        await db.commit()
