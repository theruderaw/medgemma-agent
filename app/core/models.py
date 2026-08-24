from sqlalchemy import BigInteger, Column, Index, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


class SessionRow(SQLModel, table=True):
    __tablename__ = "sessions"

    session_id: str = Field(primary_key=True)
    created_at: float
    last_activity: float


class MessageRow(SQLModel, table=True):
    __tablename__ = "messages"
    __table_args__ = (UniqueConstraint("session_id", "seq"),)

    id: int = Field(sa_column=Column(BigInteger, primary_key=True))
    session_id: str = Field(foreign_key="sessions.session_id", ondelete="CASCADE", index=True)
    seq: int
    role: str
    content: str
    created_at: float
    # Pipeline turn that produced this message — lets a restored conversation
    # re-join its audit-event timeline after a page reload.
    turn_id: str | None = None


class AuditEventRow(SQLModel, table=True):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("idx_audit_events_session", "session_id", "created_at"),
        Index("idx_audit_events_module", "module"),
    )

    id: int = Field(sa_column=Column(BigInteger, primary_key=True))
    session_id: str | None = None
    turn_id: str | None = None
    module: str
    event_type: str
    payload: dict = Field(default_factory=dict, sa_column=Column(JSONB, server_default=text("'{}'::jsonb")))
    created_at: float