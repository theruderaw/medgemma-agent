import time

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert

from ..core.db import SessionLocal
from ..core.models import MessageRow, SessionRow
from .base import SessionStore
from .models import Session


class PostgresSessionStore(SessionStore):
    """PostgreSQL-backed store.

    Sessions and messages live in relational tables. Messages are append-only:
    once written they are never updated, and a fresh session row is created per
    session_id. History is retained in full (no trimming) so that audit and
    evaluation can reconstruct complete conversations.
    """

    retains_full_history = True

    def __init__(self, url: str, timeout_seconds: float) -> None:
        self.url = url
        self.timeout_seconds = timeout_seconds

    async def get(self, session_id: str) -> Session | None:
        async with SessionLocal() as db:
            row = (await db.execute(select(SessionRow).where(SessionRow.session_id == session_id))).scalar_one_or_none()
            if row is None:
                return None
            if self._expired(row.last_activity):
                await db.execute(delete(SessionRow).where(SessionRow.session_id == session_id))
                await db.commit()
                return None

            message_rows = (
                await db.execute(
                    select(MessageRow).where(MessageRow.session_id == session_id).order_by(MessageRow.seq)
                )
            ).scalars().all()

            session = Session(
                session_id=session_id,
                messages=[
                    {"role": r.role, "content": r.content, "turn_id": r.turn_id}
                    for r in message_rows
                ],
                created_at=row.created_at,
                last_activity=row.last_activity,
            )
            session.persisted_count = len(session.messages)
            return session

    async def save(self, session: Session) -> None:
        now = time.time()
        async with SessionLocal() as db:
            await db.execute(
                insert(SessionRow)
                .values(
                    session_id=session.session_id,
                    created_at=session.created_at,
                    last_activity=now,
                )
                .on_conflict_do_update(
                    index_elements=[SessionRow.session_id],
                    set_={"last_activity": now},
                )
            )

            for seq, message in enumerate(session.messages[session.persisted_count:], start=session.persisted_count):
                await db.execute(
                    insert(MessageRow)
                    .values(
                        session_id=session.session_id,
                        seq=seq,
                        role=message["role"],
                        content=message["content"],
                        created_at=now,
                        turn_id=message.get("turn_id"),
                    )
                    .on_conflict_do_nothing(index_elements=[MessageRow.session_id, MessageRow.seq])
                )
            session.persisted_count = len(session.messages)
            session.last_activity = now
            await db.commit()

    async def delete(self, session_id: str) -> bool:
        async with SessionLocal() as db:
            result = await db.execute(delete(SessionRow).where(SessionRow.session_id == session_id))
            await db.commit()
            return result.rowcount > 0