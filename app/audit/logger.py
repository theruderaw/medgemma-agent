import time
from abc import ABC, abstractmethod
from typing import Any

from ..core.config import settings
from ..core.db import SessionLocal
from ..core.models import AuditEventRow


class AuditLogger(ABC):
    """Append-only audit sink. Implementations must never update or delete rows."""

    @abstractmethod
    async def append(
        self,
        *,
        module: str,
        event_type: str,
        payload: dict[str, Any],
        session_id: str | None = None,
        turn_id: str | None = None,
    ) -> None:
        """Record one immutable audit event."""


class NullAuditLogger(AuditLogger):
    async def append(self, **kwargs: Any) -> None:
        return None


class PostgresAuditLogger(AuditLogger):
    """Persists audit events to the append-only audit_events table.

    Only INSERT statements are issued; there is no update or delete path. Rows
    are never modified after insertion, giving an immutable audit trail.
    """

    def __init__(self, url: str) -> None:
        self.url = url

    async def append(
        self,
        *,
        module: str,
        event_type: str,
        payload: dict[str, Any],
        session_id: str | None = None,
        turn_id: str | None = None,
    ) -> None:
        async with SessionLocal() as db:
            db.add(
                AuditEventRow(
                    session_id=session_id,
                    turn_id=turn_id,
                    module=module,
                    event_type=event_type,
                    payload=payload,
                    created_at=time.time(),
                )
            )
            await db.commit()


def build_audit_logger() -> AuditLogger:
    if settings.audit_enabled:
        return PostgresAuditLogger(settings.database_url)
    return NullAuditLogger()


audit = build_audit_logger()