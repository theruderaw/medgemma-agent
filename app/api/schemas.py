from typing import Any

from pydantic import BaseModel, Field

from ..triage import Urgency


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    session_id: str | None = Field(default=None, min_length=1)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)


class AuditEvent(BaseModel):
    module: str
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    turn_id: str | None = None


class ChatResponse(BaseModel):
    session_id: str
    response: str
    urgency: Urgency | None = None
    events: list[AuditEvent] = Field(default_factory=list)